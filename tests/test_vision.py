import unittest
from pathlib import Path
from PIL import Image
from pc_lab.vision import read_state,Geometry


class VisionTests(unittest.TestCase):
    def test_falling_t_and_very_dark_gray_o_hold(self):
        folder=Path(__file__).resolve().parent.parent/'output/live-20261014-100214-b6372bdf'
        if not (folder/'stopped.png').is_file():self.skipTest('No gravity fixture')
        import json
        pending=json.loads((folder/'unfinished-step.json').read_text(encoding='utf-8'))
        state=read_state(Image.open(folder/'stopped.png'),expected_board=tuple(pending['board_before']))
        self.assertEqual(state['active'],'T')
        self.assertEqual(state['hold'],'O')
        self.assertFalse(state['hold_available'])
        self.assertEqual(min(y for x,y in state['active_cells']),18)
        self.assertEqual(state['board'],tuple(pending['board_before']))
        standalone=read_state(Image.open(folder/'stopped.png'))
        self.assertEqual(standalone['active'],'T')
        self.assertEqual(standalone['board'],tuple(pending['board_before']))
    def test_sunset_background_is_not_part_of_spawned_z(self):
        fixture=Path(__file__).resolve().parent.parent/'output/live-20261014-075838-68eff2ee/stopped.png'
        if not fixture.is_file():self.skipTest('No sunset spawn fixture')
        state=read_state(Image.open(fixture))
        self.assertEqual(state['active'],'Z')
        self.assertEqual(set(map(tuple,state['active_cells'])),{(3,22),(4,22),(4,21),(5,21)})
        self.assertEqual(state['next'],'ITJSL')
        self.assertTrue(all(row=='__________' for row in state['board']))

    def test_yellow_sprite_bevel_is_not_a_second_o_preview(self):
        fixture=Path(__file__).resolve().parent.parent/'output/live-20261014-080107-ed4d9316/preview-mismatch.png'
        if not fixture.is_file():self.skipTest('No bevel duplicate screenshot')
        state=read_state(Image.open(fixture))
        self.assertEqual(state['next'],'OTISO')
        self.assertEqual(state['preview_count'],5)
    def test_full_zen_meter_does_not_hide_board_geometry(self):
        fixture=Path(__file__).resolve().parent.parent/'output/live-20261014-001107-b15d1136/stopped.png'
        if not fixture.is_file():self.skipTest('No full ZEN meter screenshot')
        state=read_state(Image.open(fixture))
        self.assertEqual(state['active'],'I')
        self.assertEqual(state['next'],'LZSOT')
        self.assertTrue(all(row=='__________' for row in state['board']))
        self.assertEqual(state['game_mode'],'zen')
    def test_cursor_glow_does_not_merge_two_i_previews(self):
        folder=Path(__file__).resolve().parent.parent/'output/live-20261013-235642-c0d5e937'
        if not (folder/'preview-mismatch.png').is_file():self.skipTest('No cursor-glow screenshot')
        initial=read_state(Image.open(folder/'start.png'))
        state=read_state(Image.open(folder/'preview-mismatch.png'),Geometry(**initial['geometry']))
        self.assertEqual(state['next'],'ZOIIL')
        self.assertEqual(state['preview_count'],5)

    def test_zen_five_next_and_disabled_gray_hold(self):
        fixture=Path(__file__).resolve().parent.parent/'output/zen-five-gray-hold.png'
        if not fixture.is_file():self.skipTest('No ZEN screenshot')
        state=read_state(Image.open(fixture))
        self.assertEqual(state['next'],'JLOTZ')
        self.assertEqual(state['preview_count'],5)
        self.assertEqual(state['hold'],'S')
        self.assertFalse(state['hold_available'])
        self.assertEqual(state['game_mode'],'zen')
    def test_captured_empty_board_hold_and_next(self):
        fixture=Path(__file__).resolve().parent.parent/"output/game-calibration.png"
        if not fixture.is_file():self.skipTest("No local calibration screenshot")
        state=read_state(Image.open(fixture))
        self.assertEqual(state["active"],"S")
        self.assertIsNone(state["hold"])
        self.assertEqual(state["next"],"IJZLTO")
        self.assertTrue(all(row=="__________" for row in state["board"]))

    def test_seeded_capture_identifies_real_spawn_height(self):
        fixture=Path(__file__).resolve().parent.parent/"output/seeded-start.png"
        if not fixture.is_file():self.skipTest("No local seeded screenshot")
        state=read_state(Image.open(fixture))
        self.assertEqual(state["active"],"I")
        self.assertEqual(set(map(tuple,state["active_cells"])),{(3,21),(4,21),(5,21),(6,21)})
        self.assertEqual(state["next"],"TJSOLZ")


if __name__=="__main__":unittest.main()
