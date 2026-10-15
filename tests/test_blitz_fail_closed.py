import unittest
from unittest.mock import Mock
from pc_lab.blitz_live import BlitzRunner
from pc_lab.engine import empty_board,cells,load_kicks
from pc_lab.solver import ROOT


class BlitzFailClosedTests(unittest.TestCase):
    def test_balanced_also_stops_without_correction_or_drop_after_unconfirmed_route(self):
        for air in (False,True):
            with self.subTest(air=air):
                runner=object.__new__(BlitzRunner)
                runner.input_trace=[];runner.kicks=load_kicks(ROOT/'data/srsplus90.properties')
                runner.allow180=True;runner.allow_wall=True;runner.finesse_saved=0;runner.wall_inputs=0
                runner.speed=lambda:dict(frame_wait_ms=0,speed_preset='extreme')
                runner.air_eligible=Mock(return_value=air);runner.already_grounded=Mock(return_value=True)
                runner.release_soft=Mock();runner.fault_allowance=lambda:999
                runner.standard_inputs_only=lambda:False
                runner.send=Mock();runner.send_wall=Mock()
                runner.send_ground_wall=Mock()
                runner.ground_state=Mock(side_effect=AssertionError('Must not retry an unconfirmed move'))
                board=empty_board();actual=cells('O',0,4,21 if air else 0)
                state=dict(board=board,active='O',hold=None,next='ITZLJ',active_cells=actual)
                runner.latest=state
                runner.wait_for=Mock(side_effect=RuntimeError('sprite is not at expected target'))
                step=dict(piece='O',hold_used=False,hold_after=None,spin='none',cells=cells('O',0,0,0))
                with self.assertRaisesRegex(RuntimeError,'未补发或硬降'):
                    runner.ground_execute(step,state)
                runner.send.assert_not_called()
                self.assertEqual(runner.send_wall.call_count if air else runner.send_ground_wall.call_count,1)
                runner.ground_state.assert_not_called()


if __name__=='__main__':unittest.main()
