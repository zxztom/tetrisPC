import unittest
from pc_lab.openers import pco_setup,dpc_setup,dpc_patterns
from pc_lab.rng import seeded_queue
from pc_lab.dpc import seeded_dpc
from pc_lab.fast_solver import find_pc


class OpenerTests(unittest.TestCase):
    def test_standard_pco_preserves_i(self):
        q=seeded_queue(1234,35)
        setup=pco_setup(dict(enumerate(q[:7])),0,None,0)
        self.assertIsNotNone(setup)
        self.assertEqual(len(setup),6)
        self.assertEqual(setup[-1]['hold_after'],'I')
        board=setup[-1]['board_after']
        self.assertEqual(sum(c!='_' for r in board for c in r),24)
        finish=find_pc(q[setup[-1]['queue_index_after']:],rows=list(reversed(board[:4])),
                       hold='I',lines=4,mode='soft',path_mode='instant')
        self.assertEqual(finish['status'],'solved')

    def test_standard_dpc_extra_i_has_small_verified_finish(self):
        q=seeded_queue(1234,100)
        plan=seeded_dpc(q,21,0,0,35)
        self.assertEqual(plan['status'],'solved')
        self.assertEqual(len(plan['steps']),15)
        self.assertEqual(sum(len(s['cleared_rows']) for s in plan['steps']),6)
        self.assertTrue(plan.get('dpc_setup'))

    def test_finish_can_use_hold_when_cycle_queue_is_exhausted(self):
        plan=find_pc('',rows=['XXXXXXXX__','XXXXXXXX__'],hold='O',lines=2,mode='soft',path_mode='instant')
        self.assertEqual(plan['status'],'solved')
        self.assertTrue(plan['steps'][0]['hold_used'])
        self.assertEqual(plan['final_hold'],'?')

    def test_setup_data_contains_each_extra_piece_class(self):
        self.assertEqual({p['extra'] for p in dpc_patterns()},{'O','S','I','J','T'})


if __name__=='__main__':unittest.main()
