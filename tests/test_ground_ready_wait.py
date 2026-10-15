import unittest
from unittest.mock import Mock,patch
from pc_lab.blitz_live import BlitzRunner
from pc_lab.blitz import settle
from pc_lab.engine import cells,empty_board


class GroundReadyWaitTests(unittest.TestCase):
    def runner(self,preset):
        runner=object.__new__(BlitzRunner);runner.soft_held=False;runner.keys={};runner.hwnd=123
        runner.before_input=Mock();runner.speed=lambda:dict(speed_preset=preset)
        return runner

    def test_extreme_waits_for_actual_ground_and_identity_instead_of_fixed_delay(self):
        r=self.runner('extreme');board=empty_board();pose=settle(board,'T',(4,21,0))
        grounded=dict(board=board,active='T',hold='O',next='IJSZO',
                      active_cells=cells('T',pose[2],pose[0],pose[1]))
        def observe_until_ready(predicate,*args,**kwargs):
            self.assertFalse(predicate(dict(grounded,active_cells=cells('T',0,4,10))))
            self.assertFalse(predicate(dict(grounded,active='J')))
            self.assertFalse(predicate(dict(grounded,hold='L')))
            self.assertFalse(predicate(dict(grounded,next='ZJSZO')))
            self.assertFalse(predicate(dict(grounded,board=('X_________',)+board[1:])))
            self.assertTrue(predicate(grounded))
            return grounded,None
        r.wait_for=observe_until_ready
        with patch('pc_lab.blitz_live.key_event') as key, \
             patch('pc_lab.blitz_live.time.sleep',side_effect=AssertionError('no blind extreme delay')):
            result=r.ground_state(board,'T','O','I')
        self.assertIs(result,grounded)
        key.assert_called_once_with(123,'down',True,{})
        self.assertTrue(r.soft_held)

    def test_other_presets_keep_their_existing_delay(self):
        r=self.runner('steady');r.wait_for=Mock(return_value=({'ready':True},None))
        with patch('pc_lab.blitz_live.key_event'),patch('pc_lab.blitz_live.time.sleep') as pause:
            r.ground_state(empty_board())
        pause.assert_called_once_with(.018)


if __name__=='__main__':unittest.main()
