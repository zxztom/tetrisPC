import json
import unittest
from pathlib import Path

from pc_lab.engine import cells,fits,load_kicks,preferred_route,empty_board
from pc_lab.solver import ROOT,KICKS


class RotationTests(unittest.TestCase):
    def test_human_visible_three_line_endgame_uses_srsplus(self):
        from pc_lab.fast_solver import solve_fast
        result=solve_fast({'queue':'ITOZJO','hold':'S','rows':['__________','_T_______J','_TOOL_SSJJ'],
                           'target_lines':3,'mode':'soft','rotation_rules':'SRS+'})
        self.assertEqual(result['status'],'solved',result['message'])
        self.assertTrue(result['rules'].startswith('SRS+90'))
        self.assertEqual(len(result['steps']),5)
        self.assertEqual(sum(len(s['cleared_rows']) for s in result['steps']),3)
        self.assertEqual(tuple(result['steps'][-1]['board_after']),empty_board())
        kicks=load_kicks(ROOT/'data/srsplus90.properties')
        for step in result['steps']:
            route=preferred_route(tuple(step['board_before']),step['piece'],step['cells'],kicks)
            self.assertEqual(route['actions'],step['actions'])
    def test_native_i_on_z_uses_srsplus_kick_order(self):
        fixture=json.loads((ROOT/'data/i-on-z-regression.json').read_text())
        board=tuple(fixture['board']);kicks=load_kicks(ROOT/'data/srsplus90.properties')
        x,y,r=fixture['before_pose']
        for dx,dy in kicks['I.NE']:
            actual=cells('I',1,x+dx,y+dy)
            if fits(board,actual):break
        self.assertEqual(set(actual),set(map(tuple,fixture['observed_after_cw'])))

    def test_i_on_z_target_is_reached_by_air_rotation_and_drop(self):
        fixture=json.loads((ROOT/'data/i-on-z-regression.json').read_text())
        board=tuple(fixture['board']);kicks=load_kicks(ROOT/'data/srsplus90.properties')
        route=preferred_route(board,'I',fixture['target_lock'],kicks)
        self.assertNotIn('soft_drop',route['actions'])
        self.assertIn(route['actions'][0],('cw','ccw'))
        self.assertEqual(route['x'],0)
        self.assertEqual(route['actions'][-1],'hard_drop')
