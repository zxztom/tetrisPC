import unittest
from pc_lab.best_fields import field_setups
from pc_lab.engine import load_kicks
from pc_lab.finesse import estimated_faults
from pc_lab.solver import ROOT


class SetupWeightTests(unittest.TestCase):
    def test_historical_observed_preview_can_select_a_less_complex_ground_setup(self):
        # Actual preview BEFORE piece 496 of the saved native 680-piece
        # run. No seed or later replay piece is involved in this fixture.
        known={496+i:p for i,p in enumerate('ILZSIJ')};known[-1]='Z'
        kicks=load_kicks(ROOT/'data/srsplus90.properties')
        first=field_setups(known,496,-1,5,kicks,path_mode='ground180',prefer_finesse=True,finesse_weight=.5)[0]
        shorter=field_setups(known,496,-1,5,kicks,path_mode='ground180',prefer_finesse=True,finesse_weight=8)[0]
        costs=lambda plan:sum(estimated_faults(s['piece'],s['cells'],s['actions']) for s in plan)
        self.assertEqual((costs(first),costs(shorter)),(6,3))
        self.assertGreater(first[0]['source_reported_coverage'],shorter[0]['source_reported_coverage'])
        self.assertNotEqual(tuple(first[-1]['board_after']),tuple(shorter[-1]['board_after']))
