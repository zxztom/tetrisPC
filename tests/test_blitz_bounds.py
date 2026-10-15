import unittest
from pc_lab.blitz_bounds import score_envelope,level_at

class ScoreBoundsTests(unittest.TestCase):
    def test_native_level_thresholds(self):
        self.assertEqual(level_at(228),15)
        self.assertEqual(level_at(260),16)

    def test_first_three_pcs_are_four_four_six(self):
        for n,pcs in ((9,0),(10,1),(20,2),(34,2),(35,3),(70,6)):
            r=score_envelope(n,False)
            self.assertEqual(r['pcs'],pcs)
            self.assertEqual(r['completed_cycles'],n//35)
            self.assertLessEqual(r['min_score'],r['max_score'])

    def test_bonus_envelope_contains_the_zero_spin_envelope(self):
        a=score_envelope(35,False);b=score_envelope(35,True)
        self.assertLessEqual(b['min_score'],a['min_score'])
        self.assertGreaterEqual(b['max_score'],a['max_score'])

    def test_pure_four_cycle_has_seven_pcs_and_same_cell_conservation(self):
        a=score_envelope(70,False,(4,)*7);b=score_envelope(70,False)
        self.assertEqual((a['pcs'],a['lines_min'],a['lines_max']),(7,28,28))
        self.assertEqual((b['pcs'],b['lines_min'],b['lines_max']),(6,28,28))
        self.assertFalse(a['geometry_verified'])
        self.assertFalse(a['drop_points_included'])

    def test_bad_cycle_inventory_is_rejected(self):
        for cycle in ((4,), (3,4,7), (), (True,)):
            with self.subTest(cycle=cycle),self.assertRaises(ValueError):score_envelope(70,False,cycle)
        with self.assertRaises(ValueError):score_envelope(-1)

if __name__=='__main__':unittest.main()
