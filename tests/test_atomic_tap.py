import unittest
from unittest.mock import patch

from pc_lab import windows


class AtomicTapTests(unittest.TestCase):
    def test_press_and_release_are_queued_together_without_a_sleep(self):
        batches = []
        def accept(count, events, size):
            batches.append([(events[i].data.ki.wScan, events[i].data.ki.dwFlags) for i in range(count)])
            return count
        with patch.object(windows.user, 'SendInput', side_effect=accept), \
             patch.object(windows.user, 'GetForegroundWindow', return_value=123), \
             patch('pc_lab.windows.emergency_pressed', return_value=False), \
             patch('pc_lab.windows.time.sleep', side_effect=AssertionError('atomic tap cannot sleep')):
            windows.tap(123, 'right', duration=0, gap=0)
        self.assertEqual(len(batches), 1)
        self.assertEqual(len(batches[0]), 2)
        down, up = batches[0]
        self.assertEqual(down[0], up[0])
        self.assertEqual(down[1], 9)  # Scan code + extended arrow key.
        self.assertEqual(up[1], 11)  # Same key, with KEYUP.

    def test_focus_loss_or_stop_sends_nothing(self):
        for focused, stopped in ((456, False), (123, True)):
            with self.subTest(focused=focused, stopped=stopped), \
                 patch.object(windows.user, 'SendInput') as send, \
                 patch.object(windows.user, 'GetForegroundWindow', return_value=focused), \
                 patch('pc_lab.windows.emergency_pressed', return_value=False):
                with self.assertRaises(InterruptedError):
                    windows.tap(123, 'right', duration=0, gap=0, cancelled=lambda: stopped)
                send.assert_not_called()

    def test_partial_acceptance_releases_and_stops_without_retry(self):
        with patch.object(windows.user, 'SendInput', return_value=1) as send, \
             patch.object(windows.user, 'GetForegroundWindow', return_value=123), \
             patch('pc_lab.windows.emergency_pressed', return_value=False), \
             patch('pc_lab.windows.key_event') as release:
            with self.assertRaises(RuntimeError):
                windows.tap(123, 'right', duration=0, gap=0)
        self.assertEqual(send.call_count, 1)
        release.assert_called_once_with(123, 'right', False, None)


if __name__ == '__main__':
    unittest.main()
