import unittest
from unittest.mock import patch
from pc_lab.blitz_finish import promote_spin
from pc_lab.blitz import ground_locks,settle,raw_ground_action,t_spin
from pc_lab.engine import empty_board,load_kicks,cells
from pc_lab.solver import ROOT


class LocalSpinTradeoffTests(unittest.TestCase):
    def test_own_observed_field_gains_a_mini_without_changing_target_cells(self):
        board=('_SLJ_ZZOOI','_____JTSSI','_____JJS__')+empty_board()[3:]
        target=((3,1),(4,0),(4,1),(4,2));kicks=load_kicks(ROOT/'data/srsplus90.properties')
        route=ground_locks(board,'T',kicks,allow180=True,allow_wall=True,wanted=target)[target]
        old=promote_spin(board,'T',target,kicks,route)
        new=promote_spin(board,'T',target,kicks,route,extra_inputs=1)
        self.assertEqual(old['spin'],'none');self.assertEqual(new['spin'],'mini')
        pose=settle(board,'T',(4,21,0));raw=pose
        for action in new['actions'][:-1]:
            raw=raw_ground_action(board,'T',pose,action,kicks);pose=settle(board,'T',raw)
        self.assertEqual(raw,pose)
        self.assertEqual(tuple(sorted(cells('T',pose[2],pose[0],pose[1]))),target)
        self.assertEqual(t_spin(board,'T',raw,new['actions'][-2]),'mini')

    def test_default_keeps_minimum_input_route_but_opt_in_can_buy_one_rotation(self):
        route=dict(actions=['left_wall','hard_drop'],spin='none')
        spin=dict(actions=['left_wall','cw','hard_drop'],spin='full')
        def candidates(*args,**kwargs):
            return {():spin} if kwargs['wanted_spin']=='full' else {}
        with patch('pc_lab.blitz_finish.ground_locks',side_effect=candidates):
            self.assertIs(promote_spin((),'T',(),{},route),route)
            better=promote_spin((),'T',(),{},route,extra_inputs=1)
        self.assertEqual(better['spin'],'full')
        self.assertEqual(better['spin_extra_input_cost'],1)

    def test_extra_das_charge_is_not_treated_as_a_quick_rotation(self):
        route=dict(actions=['cw','hard_drop'],spin='none')
        spin=dict(actions=['left_wall','cw','hard_drop'],spin='full')
        def candidates(*args,**kwargs):
            return {():spin} if kwargs['wanted_spin']=='full' else {}
        with patch('pc_lab.blitz_finish.ground_locks',side_effect=candidates):
            self.assertIs(promote_spin((),'T',(),{},route,extra_inputs=1),route)

    def test_two_extra_inputs_still_rejected(self):
        route=dict(actions=['left_wall','hard_drop'],spin='none')
        spin=dict(actions=['left_wall','cw','ccw','hard_drop'],spin='full')
        with patch('pc_lab.blitz_finish.ground_locks',return_value={():spin}):
            self.assertIs(promote_spin((),'T',(),{},route,extra_inputs=1),route)


if __name__=='__main__':unittest.main()
