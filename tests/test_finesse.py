import json
import unittest
from pathlib import Path
from pc_lab.finesse import estimated_faults,lower_bounds,footprint
from pc_lab.engine import empty_board,cells,load_kicks
from pc_lab.blitz import ground_locks,Score
from pc_lab.blitz_finish import improve_finish
from pc_lab.solver import ROOT

class FinesseTests(unittest.TestCase):
    def test_fast_solver_preserves_verified_ground_finesse_actions(self):
        from pc_lab.fast_solver import find_pc
        from pc_lab.search_worker import close_worker
        try:
            result=find_pc('JLOSLTJ',rows=['I_________','IT________','ITTSS_____','ITSS______'],hold='Z',lines=4,
                mode='soft',path_mode='ground180fine',kick_path=ROOT/'data/srsplus90.properties',persistent=True,timeout=1.5,save=False)
            self.assertEqual(result['status'],'solved')
            self.assertTrue(all(s['finesse_standard_finish'] for s in result['steps']))
            # Previously these seven independently verified routes were
            # overwritten by preferred airborne routes totaling 7 faults.
            self.assertEqual(sum(estimated_faults(s['piece'],s['cells'],s['actions']) for s in result['steps']),0)
            self.assertEqual(tuple(result['steps'][-1]['board_after']),empty_board())
            from pc_lab.blitz_live import BlitzRunner
            runner=object.__new__(BlitzRunner);runner.request=dict(early_setup_finish=True);runner.finesse_policy='strict';runner.allow180=True
            runner.kick_path=ROOT/'data/srsplus90.properties';runner.stopped=lambda:False
            runner.pc_remaining=4;runner.early_setup_finishes=0;runner.prefix=[dict(strategy='pc_setup')]
            state=dict(board=result['initial_board'],active='J',next='LOSLTJ',hold='Z',hold_available=True)
            # Keep the actual solver result, but do not make an assertion
            # depend on a 30ms wall-clock deadline on the test machine.
            from unittest.mock import patch
            with patch('pc_lab.fast_solver.find_pc',return_value=result):
                self.assertTrue(runner.try_visible_setup_finish(state))
            self.assertEqual(len(runner.prefix),7)
        finally:close_worker()

    def visible_setup_runner(self):
        from pc_lab.blitz_live import BlitzRunner
        runner=object.__new__(BlitzRunner)
        runner.request=dict(early_setup_finish=True);runner.finesse_policy='strict';runner.allow180=True
        runner.kick_path=ROOT/'data/srsplus90.properties';runner.stopped=lambda:False
        runner.pc_remaining=2;runner.early_setup_finishes=0;runner.prefix=[dict(strategy='pc_setup')]
        board=('__XXXXXXXX','__XXXXXXXX')+empty_board()[2:]
        return runner,dict(board=board,active='O',next='ITZSJL',hold=None,hold_available=True)

    def test_visible_completion_replaces_setup_without_guessing_queue(self):
        from unittest.mock import patch
        from pc_lab.engine import lock
        runner,state=self.visible_setup_runner();target=cells('O',0,0,0)
        after,_,_=lock(state['board'],target,'O')
        proposal=dict(status='solved',steps=[dict(piece='O',cells=target,actions=['left_wall','hard_drop'],board_before=state['board'],board_after=after)])
        with patch('pc_lab.fast_solver.find_pc',return_value=proposal) as finder:
            self.assertTrue(runner.try_visible_setup_finish(state))
        self.assertEqual(finder.call_args.args[0],'OITZSJL')
        self.assertEqual(finder.call_args.kwargs['path_mode'],'ground180fine')
        self.assertEqual(runner.prefix[0]['strategy'],'pc_finish')
        self.assertEqual(runner.early_setup_finishes,1)

    def test_visible_completion_timeout_preserves_setup_and_unknown_is_not_probed(self):
        from unittest.mock import patch
        runner,state=self.visible_setup_runner();original=runner.prefix
        with patch('pc_lab.fast_solver.find_pc',side_effect=TimeoutError):
            self.assertFalse(runner.try_visible_setup_finish(state))
        self.assertIs(runner.prefix,original)
        runner.pc_remaining=6  # Eleven additional pieces: outside actual preview.
        with patch('pc_lab.fast_solver.find_pc') as finder:
            self.assertFalse(runner.try_visible_setup_finish(state))
        finder.assert_not_called()

    def test_air_window_uses_real_profile_gravity_and_state_age(self):
        from pc_lab.blitz_live import BlitzRunner
        runner=object.__new__(BlitzRunner);runner.allow_wall=True;runner.simulation='blitz';runner.score_state=Score(level=9)
        runner.observed_at=0;runner.fall_rate=0
        state=dict(board=empty_board(),active_cells=cells('O',0,4,18))
        self.assertTrue(runner.air_eligible(state))
        runner.score_state=Score(level=15);self.assertFalse(runner.air_eligible(state))
        runner.score_state=Score(level=1);runner.simulation='level10'
        self.assertAlmostEqual(runner.actual_gravity(),2.01423,places=4)
        runner.simulation='20g';self.assertFalse(runner.air_eligible(state))
        runner.simulation='blitz';runner.score_state=Score(level=9)
        import time
        runner.observed_at=time.perf_counter()-1
        self.assertFalse(runner.air_eligible(state))

    def test_adaptive_budget_is_one_fault_in_each_70_piece_window(self):
        from pc_lab.blitz_live import BlitzRunner
        runner=object.__new__(BlitzRunner);runner.steps=[];runner.finesse_policy='adaptive'
        self.assertEqual(runner.fault_allowance(),1)
        runner.steps=[dict(estimated_finesse_faults=1)]+[dict(estimated_finesse_faults=0)]*68
        self.assertEqual(runner.fault_allowance(),0)
        runner.steps.append(dict(estimated_finesse_faults=0))
        self.assertEqual(runner.fault_allowance(),1)
        runner.finesse_policy='strict';self.assertEqual(runner.fault_allowance(),0)

    def test_equivalent_s_and_i_orientations_do_not_earn_rotation_budget(self):
        for piece in 'ISZ':
            a=footprint(cells(piece,0,4,3))
            b=footprint(cells(piece,2,4 if piece!='I' else 5,4))
            # Equivalence is physical; translated targets retain their x.
            if a!=b:
                b=next(footprint(cells(piece,2,x,4)) for x in range(2,7) if footprint(cells(piece,2,x,4))==a)
            self.assertEqual(lower_bounds(piece)[a],lower_bounds(piece)[b])
            self.assertEqual(estimated_faults(piece,cells(piece,0,4,3),['cw','ccw','hard_drop']),2)

    def test_wall_shift_is_one_input_and_interior_triple_tap_is_penalized(self):
        target=cells('O',0,0,0)
        self.assertEqual(estimated_faults('O',target,['left_wall','hard_drop']),0)
        self.assertGreater(estimated_faults('O',target,['left']*4+['hard_drop']),0)

    def test_estimated_high_gravity_fault_deltas_match_native_checkpoints(self):
        source=ROOT/'output/live-20261014-213126-e7f113a2/session.json'
        replay=ROOT/'output/blitz-extreme-run5.ttr'
        if not source.exists() or not replay.exists():self.skipTest('native fixture unavailable')
        steps=json.loads(source.read_text(encoding='utf-8'))['steps']
        predicted=[estimated_faults(s['piece'],s['cells'],s['actions']) for s in steps]
        points=[e['data']['stats'] for e in json.loads(replay.read_text(encoding='utf-8'))['replay']['events']
                if e['type']=='full' and e['data']['stats']['piecesplaced']>=211]
        for a,b in zip(points,points[1:]):
            lo,hi=a['piecesplaced'],b['piecesplaced']
            self.assertEqual(sum(predicted[lo:hi]),b['finesse']['faults']-a['finesse']['faults'])
            self.assertEqual(sum(f==0 for f in predicted[lo:hi]),b['finesse']['perfectpieces']-a['finesse']['perfectpieces'])

    def test_budget_expiry_preserves_verified_pc_finish(self):
        kicks=load_kicks(ROOT/'data/srsplus90.properties');board=('__XXXXXXXX','__XXXXXXXX')+empty_board()[2:]
        route=next(iter(ground_locks(board,'O',kicks,wanted=tuple(sorted(cells('O',0,0,0))),allow_wall=True).values()))
        from pc_lab.engine import lock
        after,placed,cleared=lock(board,cells('O',0,0,0),'O')
        incumbent=[dict(piece='O',hold_used=False,hold_after=None,cells=cells('O',0,0,0),board_after=after,cleared_rows=cleared,**route)]
        self.assertIs(improve_finish(board,'O',None,kicks,Score(),2,incumbent,budget=0),incumbent)

    def test_same_native_pc_geometry_has_a_zero_fault_hold_order(self):
        from pc_lab.engine import canonicalize,reconstruct
        board=('JJJL______','JZZLLLS___','ZZJ__SS___','JJJ__S____')+empty_board()[4:]
        ops=canonicalize('I,0,5,0;T,2,8,1;Z,0,7,1;L,L,9,1;O,0,3,0',board)
        kicks=load_kicks(ROOT/'data/srsplus90.properties')
        plain=reconstruct(ops,board,'ITZLZT','O',True,kicks,'ground180')
        better=reconstruct(ops,board,'ITZLZT','O',True,kicks,'ground180fine')
        self.assertGreater(sum(estimated_faults(a['piece'],a['cells'],a['actions']) for a in plain),0)
        self.assertEqual(better[0]['piece'],'O')
        self.assertTrue(better[0]['hold_used'])
        self.assertEqual(better[-1]['board_after'],empty_board())
        self.assertEqual(sum(estimated_faults(a['piece'],a['cells'],a['actions']) for a in better),0)

if __name__=='__main__':unittest.main()
