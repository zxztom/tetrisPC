import json
import tempfile
import unittest
import shutil
from pathlib import Path
from pc_lab.farm_policy import FarmPolicy,FarmLedger,replay_result
from pc_lab.solver import ROOT


class FarmTests(unittest.TestCase):
    def test_abandoned_then_complete_attempt_exports_native_best(self):
        from pc_lab.farm_live import farm_loop
        fixture=ROOT/'output/blitz-pc-finesse-run1.ttr'
        session=ROOT/'output/live-20261014-231606-8281c190/session.json'
        if not fixture.exists() or not session.exists():self.skipTest('native fixtures unavailable')
        steps=json.loads(session.read_text(encoding='utf-8'))['steps']
        class FakeRunner:
            folder='offline-attempt'
            def __init__(self,n):self.steps=steps[:5] if n==0 else steps;self.n=n
            def run(self):return dict(status='abandoned' if self.n==0 else 'done',message='fixture',placed_pieces=len(self.steps),completed_pcs=0,estimated_clear_score=dict(score=1))
        class Nav:
            restarted=0
            def fresh_game(self,abandoned):self.restarted+=1;assert abandoned
            def export_complete(self,path):shutil.copyfile(fixture,path)
        with tempfile.TemporaryDirectory(dir=ROOT/'output') as directory:
            ledger=FarmLedger(directory);nav=Nav()
            result=farm_loop(dict(farm=dict(maximum_attempts=2)),lambda:FakeRunner(len(ledger.attempts)),nav,ledger,lambda *_:None,lambda:False)
            self.assertEqual(nav.restarted,1)
            self.assertEqual(result['farm']['best_complete']['native_score'],2236176)
            self.assertEqual(result['farm']['complete_count'],1)
            self.assertEqual(result['farm']['abandoned_count'],1)

    def test_drought_counts_verified_pieces_since_last_pc(self):
        policy=FarmPolicy(pc_drought=15)
        self.assertIsNone(policy.reason(24,[dict(pieces=10,lines=4)],1))
        self.assertIn('15',policy.reason(25,[dict(pieces=10,lines=4)],999999))
        self.assertIsNone(policy.reason(25,[dict(pieces=25,lines=10)],1))

    def test_cycle_boundaries_use_lines_as_well_as_piece_count(self):
        policy=FarmPolicy(pc_drought=0,break_cycle=True)
        for n,lines in [(10,4),(20,8),(35,14),(45,18),(55,22),(70,28)]:
            self.assertIsNone(policy.reason(n,[dict(pieces=n,lines=lines)],0))
            self.assertIsNotNone(policy.reason(n,[dict(pieces=n,lines=lines+2)],0))
        self.assertIsNone(policy.reason(9,[],0))

    def test_two_two_line_pcs_do_not_pass_strict_cycle_gate(self):
        policy=FarmPolicy(pc_drought=0,break_cycle=True)
        self.assertIsNotNone(policy.reason(10,[dict(pieces=5,lines=2),dict(pieces=10,lines=4)],0))

    def test_low_score_gate_is_after_grace_and_not_native_score(self):
        policy=FarmPolicy(pc_drought=0,grace_pieces=35,minimum_score_per_piece=100)
        self.assertIsNone(policy.reason(34,[],0))
        self.assertIn('不含下降分',policy.reason(35,[],3499))
        self.assertIsNone(policy.reason(35,[],3500))

    def test_invalid_values_rejected(self):
        for raw in [dict(pc_drought=-1),dict(pc_drought=1.5),dict(minimum_score_per_piece=float('nan')),dict(break_cycle='false')]:
            with self.assertRaises(ValueError):FarmPolicy.from_request(dict(farm=raw))

    def test_best_requires_complete_native_replay_and_never_sums_scores(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'output') as directory:
            ledger=FarmLedger(directory)
            ledger.append(dict(status='abandoned',native_score=9999999,wall_seconds=5))
            self.assertIsNone(ledger.best)
            ledger.append(dict(status='done',native_complete=True,native_replay='a.ttr',native_score=200,wall_seconds=120))
            ledger.append(dict(status='done',native_complete=True,native_replay='b.ttr',native_score=180,wall_seconds=120))
            self.assertEqual(ledger.best['native_score'],200)
            result=json.loads((Path(directory)/'summary.json').read_text(encoding='utf-8'))
            self.assertEqual((result['attempt_count'],result['complete_count'],result['abandoned_count'],result['attempt_wall_seconds']),(3,2,1,245))

    def test_native_result_uses_milliseconds_and_matches_original_replay(self):
        path=ROOT/'output/blitz-pc-finesse-run1.ttr'
        if not path.exists():self.skipTest('native fixture missing')
        result=replay_result(path)
        self.assertEqual(result['native_score'],2236176)
        self.assertTrue(result['native_complete'])

    def test_complete_game_continues_only_when_option_enabled(self):
        from pc_lab.farm_live import farm_loop
        from unittest.mock import patch
        class Runner:
            folder='synthetic-offline'
            def __init__(self,n):
                self.steps=[dict(source_index=i,piece='IJ'[n%2]) for i in range(40)]
            def run(self):return dict(status='done',message='complete',placed_pieces=40,completed_pcs=1,estimated_clear_score=dict(score=1))
        class Nav:
            restarted=0
            def fresh_game(self,abandoned):
                assert not abandoned
                self.restarted+=1
            def export_complete(self,path):pass
        for enabled in (False,True):
            with self.subTest(enabled=enabled),tempfile.TemporaryDirectory(dir=ROOT/'output') as directory:
                ledger=FarmLedger(directory);nav=Nav()
                with patch('pc_lab.farm_live.replay_result',return_value=dict(native_complete=True,native_pieces=40,native_score=100,native_replay='synthetic.ttr')):
                    result=farm_loop(dict(farm=dict(maximum_attempts=2,continue_after_complete=enabled)),
                        lambda:Runner(len(ledger.attempts)),nav,ledger,lambda *_:None,lambda:False)
                self.assertEqual(result['farm']['complete_count'],2 if enabled else 1)
                self.assertEqual(nav.restarted,1 if enabled else 0)

    def test_auto_next_rejects_non_boolean(self):
        with self.assertRaises(ValueError):FarmPolicy.from_request(dict(farm=dict(continue_after_complete='false')))

    def test_final_native_result_takes_precedence_over_older_checkpoint(self):
        checkpoint=dict(score=80,finaltime=119000,piecesplaced=40,lines=16,level=4,
                        clears=dict(allclear=2),tspins=0,finesse=dict(faults=0))
        final=dict(checkpoint,score=100,finaltime=120000)
        with tempfile.TemporaryDirectory(dir=ROOT/'output') as directory:
            path=Path(directory)/'synthetic.ttr'
            path.write_text(json.dumps(dict(gamemode='blitz',replay=dict(
                events=[dict(type='full',data=dict(stats=checkpoint))],results=dict(stats=final)))),encoding='utf-8')
            result=replay_result(path)
            self.assertTrue(result['native_complete'])
            self.assertEqual(result['native_score'],100)

    def test_recorded_menu_matches_across_resampling_but_rejects_other_screen(self):
        from PIL import Image
        from pc_lab.farm_navigation import NativeNavigator
        fixture=ROOT/'output/farm-20261015-122341-bff79ffa/menu-stop-solo.png'
        if not fixture.exists():self.skipTest('native calibration fixture unavailable')
        recipe=NativeNavigator.load_recipe()
        with Image.open(fixture) as image:
            self.assertTrue(NativeNavigator.matches(image,recipe['initial'][0]))
            self.assertFalse(NativeNavigator.matches(image,recipe['complete'][0]))
            self.assertFalse(NativeNavigator.matches(image,recipe['initial'][2]))

    def test_repeated_queue_is_rejected_even_if_game_piece_counts_differ(self):
        from unittest.mock import Mock,patch
        from pc_lab.farm_live import farm_loop
        class Runner:
            folder='synthetic-offline'
            def __init__(self,n):self.steps=[dict(source_index=i,piece='I') for i in range(40+n)]
            def run(self):return dict(status='done',message='complete',placed_pieces=len(self.steps),completed_pcs=1,estimated_clear_score=dict(score=1))
        with tempfile.TemporaryDirectory(dir=ROOT/'output') as directory:
            ledger=FarmLedger(directory);nav=Mock()
            with patch('pc_lab.farm_live.replay_result',return_value=dict(native_complete=True,native_pieces=40,native_score=100,native_replay='synthetic.ttr')):
                with self.assertRaisesRegex(RuntimeError,'35'):
                    farm_loop(dict(farm=dict(maximum_attempts=2)),lambda:Runner(len(ledger.attempts)),nav,ledger,lambda *_:None,lambda:False)
            self.assertEqual([a['status'] for a in ledger.attempts],['done','error'])
            self.assertEqual(nav.fresh_game.call_count,1)

    def test_reserved_end_window_accepts_only_one_natural_lock_with_matching_hard_drops(self):
        from unittest.mock import Mock,patch
        from pc_lab.farm_live import farm_loop
        class Runner:
            folder='synthetic-offline'
            steps=[dict(source_index=i,piece='I') for i in range(40)]
            def run(self):return dict(status='done',message='complete',placed_pieces=40,completed_pcs=1,estimated_clear_score=dict(score=1))
        for native_pieces,hard_drops,allowed in [(41,40,True),(42,40,False),(41,39,False)]:
            with self.subTest(native_pieces=native_pieces,hard_drops=hard_drops),tempfile.TemporaryDirectory(dir=ROOT/'output') as directory:
                ledger=FarmLedger(directory)
                native=dict(native_complete=True,native_pieces=native_pieces,native_hard_drops=hard_drops,native_score=100,native_replay='synthetic.ttr')
                with patch('pc_lab.farm_live.replay_result',return_value=native):
                    if allowed:
                        result=farm_loop(dict(farm=dict(maximum_attempts=1)),Runner,Mock(),ledger,lambda *_:None,lambda:False)
                        best=result['farm']['best_complete']
                        self.assertEqual((best['natural_tail_pieces'],best['verified_controlled_pieces']),(1,40))
                    else:
                        with self.assertRaisesRegex(RuntimeError,'块数不符'):
                            farm_loop(dict(farm=dict(maximum_attempts=1)),Runner,Mock(),ledger,lambda *_:None,lambda:False)

    def test_initial_menu_accepts_home_results_or_blitz_start_without_again(self):
        from unittest.mock import Mock,patch
        from pc_lab.farm_navigation import NativeNavigator
        recipe=dict(initial=[dict(role=r) for r in ('solo','blitz','start')],
                    complete=[dict(role=r) for r in ('home','solo','blitz','start')])
        for role,wanted in [('solo',['solo','blitz','start']),('home',['home','solo','blitz','start']),('start',['start'])]:
            with self.subTest(role=role):
                nav=NativeNavigator(123,recipe,lambda:False,ROOT/'output')
                nav.guard=Mock();nav.click=Mock()
                nav.matches=lambda image,step:step['role']==role
                with patch('pc_lab.windows.capture',return_value=Mock()), \
                     patch('pc_lab.windows.bounds',return_value=(0,0,3072,1920)), \
                     patch('pc_lab.windows.user.SetCursorPos'):
                    nav.fresh_game(initial=True)
                self.assertEqual([call.args[0]['role'] for call in nav.click.call_args_list],wanted)

    def test_unavailable_calibration_fails_without_game_input(self):
        from pc_lab.farm_navigation import NativeNavigator
        with tempfile.TemporaryDirectory(dir=ROOT/'output') as directory:
            with self.assertRaisesRegex(ValueError,'未发送按键'):NativeNavigator.load_recipe(Path(directory)/'missing.json')

    def test_farm_stops_on_execution_error_and_records_denominator(self):
        from pc_lab.farm_live import farm_loop
        class BadRunner:
            folder='bad-run'
            def run(self):raise RuntimeError('actual board mismatch')
        class Nav:
            def fresh_game(self,**kwargs):raise AssertionError('must not restart unsafe failure')
        with tempfile.TemporaryDirectory(dir=ROOT/'output') as directory:
            ledger=FarmLedger(directory)
            with self.assertRaisesRegex(RuntimeError,'board mismatch'):
                farm_loop({},lambda:BadRunner(),Nav(),ledger,lambda *_:None,lambda:False)
            self.assertEqual(len(ledger.attempts),1)
            self.assertEqual(ledger.attempts[0]['status'],'error')
