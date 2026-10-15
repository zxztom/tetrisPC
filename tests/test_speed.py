import json
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
import numpy as np
from PIL import Image
from pc_lab.speed import speed_settings
from pc_lab.config import optimize_config,parse_config
from pc_lab.vision import component_boxes,Geometry,read_state,aligned_board
from pc_lab.engine import empty_board,cells,load_kicks
from pc_lab.solver import ROOT


class SpeedTests(unittest.TestCase):
    def test_presets_have_distinct_pacing_and_reject_invalid_values(self):
        self.assertEqual([speed_settings(n)['target_pps'] for n in ('steady','fast','sprint')],[2,4,6])
        for value in (-1,2001,float('nan'),float('inf')):
            with self.assertRaises(ValueError):speed_settings('sprint',value)
        with self.assertRaises(ValueError):speed_settings('invalid')

    def test_configs_preserve_bindings_and_have_distinct_das(self):
        raw=json.loads((ROOT/'output/current-config.ttc').read_text(encoding='utf-8'))
        keys=parse_config(raw)['keys']
        for name,das in [('steady',6),('fast',4),('sprint',3),('extreme',3)]:
            modified=optimize_config(raw,name)
            self.assertEqual(parse_config(modified)['keys'],keys)
            self.assertEqual(modified['handling']['das'],das)
            self.assertEqual(modified['volume'],raw['volume'])
            if name!='steady':self.assertTrue(modified['handling']['cancel'])
        self.assertEqual(optimize_config(raw,'sprint')['video']['graphics'],'minimal')

    def test_short_extreme_config_requires_paired_tap_selection_and_preserves_original(self):
        raw=json.loads((ROOT/'output/current-config.ttc').read_text(encoding='utf-8'))
        original=json.dumps(raw,sort_keys=True)
        self.assertEqual(optimize_config(raw,'extreme')['handling']['das'],3)
        short=optimize_config(raw,'extreme',paired_taps=True)
        self.assertEqual(short['handling']['das'],1.5)
        self.assertEqual(parse_config(short)['keys'],parse_config(raw)['keys'])
        self.assertEqual(optimize_config(raw,'sprint',paired_taps=True)['handling']['das'],3)
        self.assertEqual(json.dumps(raw,sort_keys=True),original)

    def test_span_components_match_independent_flood_fill(self):
        rng=np.random.default_rng(5)
        for _ in range(10):
            mask=rng.random((24,31))>.65;remaining=set(map(tuple,np.argwhere(mask)));expected=[]
            while remaining:
                y,x=min(remaining);todo=[(y,x)];remaining.remove((y,x));points=[]
                while todo:
                    p=todo.pop();points.append(p);y,x=p
                    for q in [(y-1,x),(y+1,x),(y,x-1),(y,x+1)]:
                        if q in remaining:remaining.remove(q);todo.append(q)
                ys,xs=zip(*points);expected.append((min(xs),min(ys),max(xs)+1,max(ys)+1,len(points)))
            self.assertEqual(sorted(component_boxes(mask,1)),sorted(expected))

    def test_preview_shape_and_color_disagreement_is_rejected(self):
        fixture=ROOT/'output/live-20261014-111230-e0e38172/start.png'
        if not fixture.is_file():self.skipTest('No native background regression fixture')
        state=read_state(Image.open(fixture))
        self.assertEqual(state['next'],'ZOISL')

    def test_low_resolution_i_preview_is_not_skipped(self):
        fixture=ROOT/'output/live-20261014-130256-16c09beb/preview-mismatch.png'
        if not fixture.is_file():self.skipTest('No minimal graphics fixture')
        im=Image.open(fixture)
        state=read_state(im,Geometry(148.5,118.5,27.45,*im.size),game_mode='zen')
        self.assertEqual(state['next'],'SJIZL')

    def test_zen_level_up_tilt_is_distinguished_from_stable_board(self):
        folder=ROOT/'output/live-20261014-132659-8c142c44'
        if not (folder/'vision-fallback.png').is_file():self.skipTest('No ZEN tilt fixture')
        j=json.loads((folder/'session.json').read_text(encoding='utf-8'));g=Geometry(**j['geometry'])
        self.assertFalse(aligned_board(Image.open(folder/'vision-fallback.png'),g))
        self.assertTrue(aligned_board(Image.open(folder/'start.png'),g))

    def test_recognized_upgrade_animation_can_finish_after_eight_seconds(self):
        runner=self.runner();runner.animation_pending=False;count=0;state={'ready':True}
        def observe(*args):
            nonlocal count
            count+=1
            if count==1:
                runner.animation_pending=True;raise ValueError('ZEN transition')
            runner.animation_pending=False;return state,None
        runner.observe=Mock(side_effect=observe)
        with patch('pc_lab.live.time.perf_counter',side_effect=[0,.5,20]),patch('pc_lab.live.time.sleep'):
            self.assertEqual(runner.wait_for(lambda s:s['ready'],timeout=1),(state,None))

    def test_live_metrics_remain_available_during_planning(self):
        from pc_lab.server import Lab
        lab=Lab()
        def fake(request,progress,cancelled):
            request['live_metrics'].update(overall_pps=6.0,target_pps=6)
            progress('running','正在规划下一步。')
            return {'message':'done'}
        with patch('pc_lab.live.run_live',side_effect=fake):
            job=lab.start(dict(kind='live',speed_preset='sprint'))
            lab.workers[-1].join(2)
        self.assertEqual(lab.snapshot(job)['metrics']['overall_pps'],6.0)

    def test_warm_solver_reuses_process_and_recovers_after_cancellation(self):
        from pc_lab.fast_solver import find_pc
        from pc_lab.search_worker import close_worker,_local
        try:
            first=find_pc('JLOSTZIJLO',persistent=True,save=False)
            pid=_local.worker.process.pid
            second=find_pc('IIIII',lines=2,persistent=True,save=False)
            self.assertEqual(first['status'],'solved');self.assertEqual(second['status'],'no_solution')
            self.assertEqual(_local.worker.process.pid,pid)
            with self.assertRaises(InterruptedError):find_pc('JLOSTZIJLO',persistent=True,save=False,cancelled=lambda:True)
            self.assertIsNotNone(_local.worker.process.poll())
            self.assertEqual(find_pc('JLOSTZIJLO',persistent=True,save=False)['status'],'solved')
            self.assertNotEqual(_local.worker.process.pid,pid)
        finally:close_worker()

    def runner(self):
        from pc_lab.live import Runner
        runner=Runner.__new__(Runner);runner.send=Mock();runner.timing={'operation_interval_ms':3,'speed_preset':'sprint'}
        runner.request={};runner.kicks=load_kicks(ROOT/'data/srsplus90.properties');runner.folder=Mock()
        runner.profile={'handling':{'sdf':41}};runner.fall_rate=0;runner.completed_pcs=0;runner.preview_count=5
        return runner

    def test_missed_air_movement_is_corrected_from_current_pose(self):
        runner=self.runner();board=empty_board();step={'cells':cells('I',0,3,0)}
        def state(x):return dict(board=board,active='I',active_cells=cells('I',0,x,21),hold=None,next='JLOST')
        frames=iter([state(4),state(3)])
        def wait(predicate,*args,**kwargs):
            value=next(frames);self.assertTrue(predicate(value));return value,None
        runner.wait_for=Mock(side_effect=wait)
        actions,_=runner.repair_burst(board,'I',step,'JLOST',None,['left'],(4,21,0))
        self.assertEqual([c.args[0] for c in runner.send.call_args_list],['left','hard_drop'])
        self.assertTrue(step['burst_repaired'])
        self.assertEqual(step['correction_actions'],['left'])

    def test_natural_lock_uses_planning_failure_and_never_sends_hard_drop(self):
        from pc_lab.live import PlanningFailure
        runner=self.runner();runner.wait_for=Mock(side_effect=RuntimeError('changed'))
        runner.latest=dict(hold=None,next='LOSTZ',board=('IIII______',)+empty_board()[1:])
        with self.assertRaises(PlanningFailure):runner.repair_burst(empty_board(),'I',{},'JLOST',None,[],(4,21,0))
        runner.send.assert_not_called()

    def test_fallen_piece_without_route_can_use_opt_in_recovery(self):
        from pc_lab.live import PlanningFailure
        runner=self.runner();board=empty_board()
        state=dict(active='I',active_cells=cells('I',0,4,0),hold=None,next='JLOST')
        step=dict(piece='I',hold_used=False,cells=cells('I',1,0,2),execution_progress=[])
        with patch('pc_lab.live.preferred_route',side_effect=ValueError('unreachable')):
            with self.assertRaises(PlanningFailure):runner.burst_piece(state,step,board,None)
        runner.send.assert_not_called()

    def test_sprint_surface_tuck_still_checks_projection_before_lock(self):
        runner=self.runner();board=empty_board();step={'piece':'I','hold_used':False,'cells':cells('I',0,3,0),'execution_progress':[]}
        state=dict(board=board,active='I',active_cells=cells('I',0,4,21),hold=None,next='JLOST')
        def wait(predicate,*args,**kwargs):
            self.assertNotIn('hard_drop',[c.args[0] for c in runner.send.call_args_list])
            actual=dict(state,active_cells=cells('I',0,3,0));self.assertTrue(predicate(actual));return actual,None
        runner.wait_for=Mock(side_effect=wait)
        with patch('pc_lab.live.preferred_route',return_value={'actions':['soft_drop','left','hard_drop']}):
            runner.burst_piece(state,step,board,None)
        self.assertEqual([c.args[0] for c in runner.send.call_args_list],['down','left','hard_drop'])


if __name__=='__main__':unittest.main()
