import unittest
from pc_lab.fast_solver import find_pc
from pc_lab.search_worker import close_worker
from pc_lab.solver import ROOT
from pc_lab.engine import empty_board
from pc_lab.finesse import estimated_faults


class TwoRowPcTests(unittest.TestCase):
    def test_known_midbag_inventory_has_a_verified_standard_five_piece_pc(self):
        # Repeated O cannot come from one fresh bag; this is an isolated
        # geometry regression, never a seeded native game or future queue.
        try:
            plan=find_pc('OOLJITS',lines=2,mode='soft',path_mode='ground180fine',
                kick_path=ROOT/'data/srsplus90.properties',timeout=1.5,persistent=True,save=False)
            self.assertEqual(plan['status'],'solved')
            self.assertEqual(len(plan['steps']),5)
            self.assertEqual(tuple(plan['steps'][-1]['board_after']),empty_board())
            self.assertEqual(sum(len(s['cleared_rows']) for s in plan['steps']),2)
            self.assertEqual(sum(estimated_faults(s['piece'],s['cells'],s['actions']) for s in plan['steps']),0)
        finally:close_worker()
