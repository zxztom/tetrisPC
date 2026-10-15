import unittest
from unittest.mock import patch
from PIL import Image
from pc_lab.farm_navigation import NativeNavigator
from pc_lab.solver import ROOT


class FarmPointerCalibrationTests(unittest.TestCase):
    def test_move_delivers_an_actual_mouse_event_after_repositioning(self):
        from pc_lab.windows import user,INPUT
        import ctypes
        received=[]
        def accept(count,pointer,size):
            event=ctypes.cast(pointer,ctypes.POINTER(INPUT)).contents
            received.append((event.type,event.data.mi.dx,event.data.mi.dy,event.data.mi.dwFlags))
            return 1
        with patch.object(user,'SetCursorPos',return_value=1) as position,patch.object(user,'SendInput',side_effect=accept):
            NativeNavigator.move_pointer(1450,850)
        position.assert_called_once_with(1450,850)
        self.assertEqual(received,[(0,1,0,1)])

    def test_result_back_without_pointer_glow_matches_calibration(self):
        fixture=ROOT/'output/farm-20261015-133328-b4897a48/menu-stop-home.png'
        if not fixture.exists():self.skipTest('native menu fixture unavailable')
        step=NativeNavigator.load_recipe()['complete'][0]
        with Image.open(fixture) as image:
            self.assertTrue(NativeNavigator.matches(image,step))
            # The two independent guards still reject a different menu.
            unrelated=Image.new('RGB',image.size,(0,0,0))
            self.assertFalse(NativeNavigator.matches(unrelated,step))


if __name__=='__main__':unittest.main()
