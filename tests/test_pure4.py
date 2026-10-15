import unittest,json
from collections import Counter

from pc_lab.cycles import cycle_spec,PURE4_BAG_GROUPS
from pc_lab.best_fields import fields,field_setups
from pc_lab.engine import load_kicks,empty_board
from pc_lab.loop import plan_loop
from pc_lab.solver import ROOT


class PureFourTests(unittest.TestCase):
    def test_seven_four_line_pcs_align_with_ten_seven_bags(self):
        stages,size=cycle_spec('pure4')
        self.assertEqual(stages,(4,)*7)
        self.assertEqual(size,70)
        self.assertEqual(sum(stages),28)
        self.assertEqual(PURE4_BAG_GROUPS,('7+3','4+6','1+7+2','5+5','2+7+1','6+4','3+7'))

    def test_imported_four_piece_fields_have_exact_piece_identity(self):
        data=fields();self.assertGreater(len(data),1000)
        for field in data:
            actual=Counter(c for row in field['rows'] for c in row if c!='_')
            self.assertEqual(actual,Counter({p:4*n for p,n in Counter(field['signature']).items()}))
            self.assertEqual(len(field['operations'][0]),4)

    def test_setup_obeys_actual_order_and_srsplus_reachability(self):
        known=dict(enumerate('ZITJSLO'))
        before=dict(known)
        plans=field_setups(known,0,None,1,load_kicks(ROOT/'data/srsplus90.properties'))
        self.assertTrue(plans)
        self.assertEqual(known,before)
        for plan in plans:
            self.assertEqual(len(plan),4)
            self.assertEqual(tuple(plan[0]['board_before']),empty_board())
            self.assertTrue(all('down' not in s['actions'] for s in plan))
            self.assertEqual(sum(c!='_' for row in plan[-1]['board_after'] for c in row),16)

    def test_seven_pc_offline_sample_tracks_all_seventy_sources(self):
        file=ROOT/'output/pure4-offline-test.json'
        if not file.is_file():self.skipTest('No seven-PC fixture')
        queue=json.loads(file.read_text(encoding='utf-8'))['queue']
        result=plan_loop({'queue':queue,'cycle_mode':'pure4','rotation_rules':'SRS+','mode':'soft'})
        self.assertEqual(result['status'],'solved',result['message'])
        self.assertEqual(len(result['steps']),70)
        self.assertEqual(sorted(s['source_index'] for s in result['steps']),list(range(70)))
        pcs=[i+1 for i,s in enumerate(result['steps']) if tuple(s['board_after'])==empty_board()]
        self.assertEqual(pcs,list(range(10,71,10)))
        self.assertEqual(result['total_cleared_lines'],28)


if __name__=='__main__':unittest.main()
