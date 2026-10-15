import unittest,time
from unittest.mock import patch
from pc_lab.engine import empty_board,lock
from pc_lab.online import choose_plan
from pc_lab.forecast_coverage import move_key,compare_first_moves


class ForecastCoverageTests(unittest.TestCase):
    def steps(self):
        result=[]
        for x,actions in ((0,['left_wall','hard_drop']),(6,['right','right','hard_drop'])):
            target=tuple((x+i,0) for i in range(4));after,placed,cleared=lock(empty_board(),target,'I')
            result.append(dict(piece='I',hold_used=False,hold_after=None,queue_index_after=1,
                cells=target,actions=actions,board_before=empty_board(),board_after=after,
                board_placed=placed,cleared_rows=cleared))
        return result

    def test_cross_checks_coverages_rather_than_first_solution_votes(self):
        a,b=self.steps();queues=['IJLOSTZJLOI','IJLOSTZLJOI','IJLOSTZOIJL']
        def solver(queue,rows,**kw):
            if all(r=='__________' for r in rows):
                return dict(status='solved',steps=[a if queue in queues[:2] else b,a])
            # A was returned first twice but fails on the third tail;
            # B is independently completable for every sampled tail.
            return dict(status='no_solution' if rows[-1].startswith('IIII') and queue==queues[2][1:] else 'solved')
        with patch('pc_lab.online.complete_bags',side_effect=queues),patch('pc_lab.online.find_pc',side_effect=solver),patch('pc_lab.forecast_coverage.find_pc',side_effect=solver):
            result=choose_plan(dict(enumerate('IJLOSTZ')),0,None,empty_board(),4,35,samples=3,coverage=True,time_budget=1)
        self.assertEqual(len(result),1)
        self.assertEqual(move_key(result[0]),move_key(b))
        self.assertEqual(result[0]['coverage_successes'],3)
        self.assertEqual(result[0]['coverage_samples'],3)
        self.assertEqual(result[0]['forecast_support'],1)
        self.assertTrue(result[0]['coverage_changed'])
        self.assertTrue(result[0]['future_was_unknown'])

    def test_incomplete_or_budget_expired_comparison_cannot_replace_incumbent(self):
        a,b=self.steps();votes={move_key(a):dict(step=a),move_key(b):dict(step=b)}
        cases=[('IJLOSTZJLOI',move_key(a))]
        with patch('pc_lab.forecast_coverage.find_pc',return_value=dict(status='incomplete')):
            self.assertIsNone(compare_first_moves(votes,cases,4,time.perf_counter()+1))
        with patch('pc_lab.forecast_coverage.find_pc') as solver:
            self.assertIsNone(compare_first_moves(votes,cases,4,time.perf_counter()-1))
            solver.assert_not_called()

    def test_cancel_is_not_an_unsolvable_tail(self):
        a,b=self.steps();votes={move_key(a):dict(step=a),move_key(b):dict(step=b)}
        with self.assertRaises(InterruptedError):
            compare_first_moves(votes,[('IJLOSTZJLOI',move_key(a))],4,time.perf_counter()+1,cancelled=lambda:True)
