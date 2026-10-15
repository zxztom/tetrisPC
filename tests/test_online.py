import unittest
from unittest.mock import patch

from pc_lab.engine import empty_board
from pc_lab.online import choose_plan,observation_consistent,resolve_observed_hold
from pc_lab.openers import pco_setup
from pc_lab.rng import seeded_queue


class OnlineTests(unittest.TestCase):
    def test_symbolic_final_carry_binds_only_current_observed_piece(self):
        step=dict(piece='I',hold_used=True,hold_before='I',hold_after='?')
        resolved=resolve_observed_hold(step,dict(active='T',hold='I'))
        self.assertEqual(resolved['hold_after'],'T')
        self.assertEqual(step['hold_after'],'?')
        self.assertEqual(resolve_observed_hold(dict(piece='O',hold_used=False,hold_before='?',hold_after='?'),dict(active='O',hold='Z'))['hold_after'],'Z')
        with self.assertRaises(ValueError):resolve_observed_hold(dict(step,piece='?'),dict(active='T',hold='I'))
        with self.assertRaises(ValueError):resolve_observed_hold(step,dict(active='?',hold='I'))
        with self.assertRaises(ValueError):resolve_observed_hold(dict(piece='O',hold_used=False,hold_after='?'),dict(active='O',hold=None))

    def test_new_preview_must_agree_with_old_cells_and_seven_bag(self):
        known=dict(enumerate('IJLOSTZ'))
        self.assertTrue(observation_consistent(known,{7:'O',8:'I'}))
        self.assertFalse(observation_consistent(known,{6:'S',7:'O'}))
        self.assertFalse(observation_consistent(known,{7:'O',8:'O'}))
        self.assertEqual(known,dict(enumerate('IJLOSTZ')))

    def test_observed_finish_is_kept_as_a_complete_route(self):
        q=seeded_queue(1234,35)
        prefix=pco_setup(dict(enumerate(q[:7])),0,None,0)
        current=prefix[-1]['queue_index_after']
        known=dict(enumerate(q[:current+7]))
        route=choose_plan(known,current,0,tuple(prefix[-1]['board_after']),4,35)
        self.assertEqual(len(route),4)
        self.assertTrue(all(not s['future_was_unknown'] for s in route))
        self.assertEqual(tuple(route[-1]['board_after']),empty_board())

    def test_unknown_future_route_executes_only_its_observed_first_move(self):
        step={'piece':'I','hold_used':False,'cells':[(0,0),(1,0),(2,0),(3,0)],'actions':['hard_drop']}
        with patch('pc_lab.online.find_pc',return_value={'status':'solved','steps':[step,dict(step,piece='J')]}):
            route=choose_plan(dict(enumerate('IJLOSTZ')),0,None,empty_board(),4,35,2)
        self.assertEqual(len(route),1)
        self.assertTrue(route[0]['future_was_unknown'])


if __name__=='__main__':unittest.main()
