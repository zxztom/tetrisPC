import ctypes,unittest
from unittest.mock import Mock,patch
from pc_lab.farm_navigation import NativeNavigator
from pc_lab.windows import user,INPUT


class FarmSaveTests(unittest.TestCase):
    def test_native_default_save_requires_guards_and_sends_one_paired_enter(self):
        navigator=object.__new__(NativeNavigator);navigator.wait=Mock();navigator.guard=Mock()
        received=[]
        def accept(count,pointer,size):
            event=ctypes.cast(pointer,ctypes.POINTER(INPUT)).contents
            received.append((event.type,event.data.ki.wVk,event.data.ki.dwFlags));return 1
        step=dict(role='save')
        with patch.object(user,'SendInput',side_effect=accept),patch('pc_lab.farm_navigation.time.sleep'):
            navigator.confirm_save(step)
        navigator.wait.assert_called_once_with(step);navigator.guard.assert_called_once_with(True)
        self.assertEqual(received,[(1,0x0D,0),(1,0x0D,2)])

    def test_unconfirmed_or_unowned_dialog_cannot_receive_enter(self):
        for blocked in ('wait','guard'):
            navigator=object.__new__(NativeNavigator);navigator.wait=Mock();navigator.guard=Mock()
            getattr(navigator,blocked).side_effect=InterruptedError('dialog not confirmed')
            with patch.object(user,'SendInput') as send,self.assertRaises(InterruptedError):
                navigator.confirm_save(dict(role='save'))
            send.assert_not_called()


if __name__=='__main__':unittest.main()
