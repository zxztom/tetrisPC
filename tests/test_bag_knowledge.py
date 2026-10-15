import itertools,unittest
from unittest.mock import patch
from pc_lab.bag_knowledge import infer_unique_remainders
from pc_lab.engine import empty_board
from pc_lab.online import choose_plan


class BagKnowledgeTests(unittest.TestCase):
    def test_every_bag_permutation_and_missing_position_is_unique(self):
        for pieces in itertools.permutations('IJLOSTZ'):
            complete=dict(enumerate(pieces,14))
            for index in range(14,21):
                known={i:p for i,p in complete.items() if i!=index}
                inferred,proofs=infer_unique_remainders(known)
                self.assertEqual(inferred,complete)
                self.assertEqual(known,{i:p for i,p in complete.items() if i!=index})
                self.assertEqual(set(proofs),{index})
                self.assertEqual(len(proofs[index]['established_members']),6)

    def test_multiple_unknowns_cross_bag_members_and_bad_bags_are_not_inferred(self):
        known={0:'I',1:'J',2:'L',3:'O',4:'S',7:'T',8:'Z'}
        self.assertEqual(infer_unique_remainders(known),(known,{}))
        self.assertEqual(infer_unique_remainders({} ),({},{}))
        for known in ({0:'I',1:'I'},{0:'?'},{0:'IJ'}):
            with self.assertRaises(ValueError):infer_unique_remainders(known)

    def test_planner_keeps_proven_finish_without_mutating_observations(self):
        # Four placements remain. All seven source members except index 6
        # are established, so source 6=Z is a proof, not a forecast.
        known={i:p for i,p in enumerate('IJLOST')}
        step=dict(piece='O',hold_used=False,cells=((0,0),(1,0),(0,1),(1,1)),actions=['hard_drop'])
        with patch('pc_lab.online.find_pc',return_value=dict(status='solved',steps=[step]*4)) as solver:
            plan=choose_plan(known,3,None,('XXXXXX____',)*4+empty_board()[4:],4,7,
                             time_budget=1,deduce_bag=True)
        self.assertEqual(solver.call_args.args[0],'OSTZ')
        self.assertEqual(len(plan),4)
        self.assertFalse(plan[0]['future_was_unknown'])
        self.assertEqual(plan[0]['seven_bag_deductions'][0]['piece'],'Z')
        self.assertNotIn(6,known)

    def test_ambiguous_later_bags_still_commit_one_move_and_keep_same_hypotheses(self):
        known=dict(enumerate('IJLOST'))
        step=dict(piece='I',hold_used=False,cells=((0,0),(1,0),(2,0),(3,0)),actions=['hard_drop'])
        arguments=[]
        for enabled in (False,True):
            with patch('pc_lab.online.find_pc',return_value=dict(status='solved',steps=[step]*10)) as solver:
                plan=choose_plan(known,0,None,empty_board(),4,35,samples=3,deduce_bag=enabled)
            self.assertEqual(len(plan),1)
            self.assertTrue(plan[0]['future_was_unknown'])
            arguments.append([call.args[0] for call in solver.call_args_list])
        self.assertEqual(*arguments)


if __name__=='__main__':unittest.main()
