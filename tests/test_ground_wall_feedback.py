import unittest
from unittest.mock import Mock,patch
from pc_lab.blitz_live import BlitzRunner
from pc_lab.engine import empty_board,cells


class GroundWallFeedbackTests(unittest.TestCase):
    def runner(self):
        r=object.__new__(BlitzRunner);r.hwnd=123;r.keys={};r.input_trace=[]
        r.before_input=Mock();r.interval_ms=lambda:0;r.stopped=lambda:False
        r.profile=dict(handling=dict(das=0,dcd=0))
        return r

    def test_holds_one_direction_until_actual_arrival_and_checks_identity_board_and_hold(self):
        r=self.runner();board=empty_board();target=cells('I',0,1,0)
        def confirm(predicate,expected_board,timeout,abort_if):
            valid=dict(board=board,active='I',hold='J',active_cells=target)
            self.assertFalse(predicate(dict(valid,active_cells=cells('I',0,3,0))))
            self.assertFalse(predicate(dict(valid,active='T')))
            self.assertFalse(predicate(dict(valid,hold='O')))
            self.assertFalse(predicate(dict(valid,board=('X_________',)+board[1:])))
            self.assertTrue(predicate(valid))
            self.assertFalse(abort_if(valid))
            self.assertTrue(abort_if(dict(valid,active='T')))
            self.assertTrue(abort_if(dict(valid,board=('X_________',)+board[1:])))
            return valid,None
        r.wait_for=Mock(side_effect=confirm)
        with patch('pc_lab.blitz_live.key_event') as key:
            r.send_ground_wall('left',board,'I','J',(1,0,0))
        self.assertEqual([call.args[2] for call in key.call_args_list],[True,False])
        self.assertTrue(r.input_trace[0]['wall_sprite_confirmed'])
        self.assertEqual(r.input_trace[0]['action'],'left_wall')

    def test_timeout_releases_key_without_rotation_retry_or_hard_drop(self):
        r=self.runner();r.wait_for=Mock(side_effect=RuntimeError('wall never arrived'));r.send=Mock()
        with patch('pc_lab.blitz_live.key_event') as key,self.assertRaises(RuntimeError):
            r.send_ground_wall('left',empty_board(),'I',None,(1,0,0))
        self.assertEqual([call.args[2] for call in key.call_args_list],[True,False])
        self.assertFalse(r.input_trace[0]['wall_sprite_confirmed']);r.send.assert_not_called()


if __name__=='__main__':unittest.main()
