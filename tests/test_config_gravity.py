import json
import unittest
from pathlib import Path
from pc_lab.config import GUIDELINE,parse_config,optimize_config,key_code
from pc_lab.engine import cells,empty_board,load_kicks,preferred_route,poses_for,dropped_cells,falls_to

ROOT=Path(__file__).resolve().parent.parent

class ConfigTests(unittest.TestCase):
    def test_actual_export_roundtrip_preserves_unrelated_preferences(self):
        raw=json.loads((ROOT/'output/user-original-20261014.ttc').read_text())
        result=optimize_config(raw)
        self.assertEqual(result['controls'],raw['controls'])
        self.assertEqual(result['video'],raw['video'])
        self.assertEqual(result['volume'],raw['volume'])
        self.assertEqual(result['handling']['sdf'],41)
        self.assertEqual(raw['handling']['arr'],2)
    def test_custom_bindings_override_every_default(self):
        bindings=dict(GUIDELINE,moveLeft=['KEYQ'],moveRight=['KEYE'],rotateCW=['KEYD'],
                      rotateCCW=['KEYA'],hold=['CAPSLOCK'],hardDrop=['KEYW'],retry=['KEYN'])
        p=parse_config({'controls':{'style':'custom','custom':bindings},'handling':{}})
        self.assertEqual(p['keys']['left'],ord('Q'))
        self.assertEqual(p['keys']['retry'],ord('N'))
        self.assertEqual(p['keys']['hold'],0x14)
    def test_wasd_matches_actual_official_layout(self):
        p=parse_config({'controls':{'style':'wasd'},'handling':{}})
        self.assertEqual((p['keys']['down'],p['keys']['hard_drop']),(ord('W'),ord('S')))
        self.assertEqual((p['keys']['cw'],p['keys']['ccw']),(0x27,0x25))
    def test_unsupported_duplicate_and_emergency_bindings_are_rejected(self):
        for change in ({'hardDrop':['PAD0-BUTTON0']},{'hardDrop':['ARROWLEFT']},{'hardDrop':['F8']}):
            with self.assertRaises(ValueError):
                parse_config({'controls':{'style':'custom','custom':dict(GUIDELINE,**change)},'handling':{}})
        with self.assertRaises(ValueError):parse_config({'g':0})
        self.assertEqual(key_code('NUMPADENTER'),0x10D)

class GravityTests(unittest.TestCase):
    def test_route_starts_at_real_height_and_rotation(self):
        board=empty_board();kicks=load_kicks(ROOT/'data/srsplus90.properties')
        target=cells('I',3,0,1)
        pose=(4,12,0)
        route=preferred_route(board,'I',target,kicks,pose)
        self.assertEqual(route['actions'][-1],'hard_drop')
        self.assertEqual(set(poses_for('I',cells('I',0,4,12))),{(4,12,0),(5,12,2)})
    def test_gravity_is_vertical_only_and_cannot_cross_stack(self):
        a=cells('T',0,4,12);b=cells('T',0,4,8)
        self.assertTrue(falls_to(empty_board(),'T',a,b))
        self.assertFalse(falls_to(empty_board(),'T',a,cells('T',0,5,8)))
        self.assertFalse(falls_to(empty_board(),'T',b,a))
        board=list(empty_board());board[10]='____X_____'
        self.assertFalse(falls_to(tuple(board),'T',a,b))
    def test_ground_pose_cannot_reach_a_blocked_air_only_target(self):
        board=list(empty_board());board[0]='___XX_____';board=tuple(board)
        self.assertEqual(set(dropped_cells(board,'O',(4,12,0))),set(cells('O',0,4,1)))

if __name__=='__main__':unittest.main()
