import unittest
from pc_lab.loop_tracker import dpc_cycles


class LoopTrackerTests(unittest.TestCase):
    def sources(self,n):return [dict(source_index=i) for i in range(n)]
    def points(self,p):return [dict(pieces=n,lines=n*2//5) for n in p]

    def test_exact_loops_have_source_and_consecutive_proof(self):
        result=dpc_cycles(self.points([10,20,35,45,55,70]),self.sources(70))
        self.assertEqual(result['verified_cycles'],2)
        self.assertEqual(result['maximum_consecutive_cycles'],2)
        self.assertEqual(result['current_consecutive_cycles'],2)

    def test_failed_first_loop_does_not_prevent_later_valid_loop(self):
        result=dpc_cycles(self.points([20,35,45,55,70]),self.sources(70))
        self.assertEqual(result['verified_cycles'],1)
        self.assertEqual(result['cycles'][0]['phase'],2)
        self.assertEqual(result['maximum_consecutive_cycles'],1)

    def test_extra_two_line_pc_is_not_a_three_pc_cycle(self):
        result=dpc_cycles(self.points([10,20,35,40,45,55,70]),self.sources(70))
        self.assertEqual(result['verified_cycles'],1)
        self.assertEqual(result['current_consecutive_cycles'],0)

    def test_same_piece_and_line_boundaries_do_not_prove_five_bags(self):
        sources=self.sources(35);sources[-1]=dict(source_index=35)
        self.assertEqual(dpc_cycles(self.points([10,20,35]),sources)['verified_cycles'],0)
        sources[-1]=dict(source_index=33)
        self.assertEqual(dpc_cycles(self.points([10,20,35]),sources)['verified_cycles'],0)

    def test_partial_expected_pc_preserves_streak_and_wrong_pc_breaks_it(self):
        self.assertEqual(dpc_cycles(self.points([10,20,35,45]),self.sources(45))['current_consecutive_cycles'],1)
        self.assertEqual(dpc_cycles(self.points([10,20,35,40]),self.sources(40))['current_consecutive_cycles'],0)

    def test_missing_start_pc_or_source_cannot_manufacture_recovery(self):
        self.assertEqual(dpc_cycles(self.points([45,55,70]),self.sources(70))['verified_cycles'],0)
        sources=self.sources(35);sources[3]={}
        self.assertEqual(dpc_cycles(self.points([10,20,35]),sources)['verified_cycles'],0)

    def test_missed_boundary_breaks_streak_without_waiting_for_another_pc(self):
        result=dpc_cycles(self.points([10,20,35,45]),self.sources(55))
        self.assertEqual(result['verified_cycles'],1)
        self.assertEqual(result['current_consecutive_cycles'],0)
        self.assertEqual(result['maximum_consecutive_cycles'],1)
