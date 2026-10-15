import json,unittest
from unittest.mock import Mock
from pc_lab.blitz_live import BlitzRunner
from pc_lab.blitz import ground_action,raw_ground_action,settle
from pc_lab.engine import cells,load_kicks
from pc_lab.solver import ROOT


class GroundSettleBarrierTests(unittest.TestCase):
    def test_same_frame_rotations_reproduce_real_wrong_native_footprint(self):
        c=json.loads((ROOT/'data/ground-settle-regression.json').read_text(encoding='utf-8'))
        board=tuple(c['board']);kicks=load_kicks(ROOT/'data/srsplus90.properties');piece=c['piece']
        wall=ground_action(board,piece,tuple(c['start']),'right_wall',kicks)
        raw=raw_ground_action(board,piece,wall,'cw',kicks);fallen=settle(board,piece,raw)
        self.assertEqual(raw[1]-fallen[1],2)
        proper=ground_action(board,piece,fallen,'cw180',kicks)
        batched=settle(board,piece,raw_ground_action(board,piece,raw,'cw180',kicks))
        self.assertEqual(sorted(cells(piece,proper[2],proper[0],proper[1])),sorted(map(tuple,c['target'])))
        self.assertEqual(sorted(cells(piece,batched[2],batched[0],batched[1])),sorted(map(tuple,c['observed_cells'])))
        self.assertNotEqual(proper,batched)
        runner=object.__new__(BlitzRunner)
        def confirm(predicate,expected,timeout,abort_if):
            state=dict(board=board,active=piece,hold='I',active_cells=cells(piece,raw[2],raw[0],raw[1]))
            self.assertFalse(predicate(state))
            state['active_cells']=cells(piece,fallen[2],fallen[0],fallen[1])
            self.assertTrue(predicate(state));self.assertFalse(abort_if(state))
            self.assertTrue(abort_if(dict(state,active='O')))
            return state,None
        runner.wait_for=Mock(side_effect=confirm)
        runner.confirm_ground_settle(board,piece,'I',fallen)

    def test_executor_does_not_send_second_rotation_when_intermediate_fall_is_unconfirmed(self):
        c=json.loads((ROOT/'data/ground-settle-regression.json').read_text(encoding='utf-8'))
        runner=object.__new__(BlitzRunner);runner.kicks=load_kicks(ROOT/'data/srsplus90.properties')
        runner.allow180=runner.allow_wall=True;runner.input_trace=[];runner.finesse_saved=runner.wall_inputs=0
        runner.speed=lambda:dict(speed_preset='extreme',frame_wait_ms=0)
        runner.air_eligible=lambda *args:False;runner.already_grounded=lambda state:True
        runner.fault_allowance=lambda:999;events=[]
        runner.send_ground_wall=Mock(side_effect=lambda *args:events.append('right_wall'))
        runner.send=Mock(side_effect=lambda action,**kw:events.append(action))
        def stop(*args):events.append('settle');raise RuntimeError('intermediate fall unconfirmed')
        runner.confirm_ground_settle=Mock(side_effect=stop)
        state=dict(board=tuple(c['board']),active=c['piece'],hold='I',next='OLITL',
            active_cells=cells(c['piece'],c['start'][2],c['start'][0],c['start'][1]))
        step=dict(piece=c['piece'],hold_used=False,hold_after='I',spin='none',cells=c['target'])
        with self.assertRaisesRegex(RuntimeError,'intermediate fall unconfirmed'):
            runner.ground_execute(step,state)
        self.assertEqual(events,['right_wall','cw','settle'])
        self.assertFalse(step['ground_settle_barriers'][0]['confirmed'])
        self.assertEqual(step['attempted_ground_actions'],['right_wall','cw'])


if __name__=='__main__':unittest.main()
