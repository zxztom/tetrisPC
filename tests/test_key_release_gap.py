import unittest
from unittest.mock import Mock, patch
from pc_lab.live import Runner


class KeyReleaseGapTests(unittest.TestCase):
    def runner(self, previous):
        runner=object.__new__(Runner)
        runner.input_trace=[{'action':previous}]
        runner.input_released=100.0
        runner.interval_ms=lambda:0
        runner.stopped=Mock(return_value=False)
        return runner

    def elapsed(self,previous,action):
        now=[100.0]
        runner=self.runner(previous)
        with patch('pc_lab.live.time.perf_counter',side_effect=lambda:now[0]), \
             patch('pc_lab.live.time.sleep',side_effect=lambda value:now.__setitem__(0,now[0]+value)):
            runner.before_input(action)
        return now[0]-100.0

    def test_repeated_tap_and_wall_to_same_key_get_a_neutral_frame(self):
        self.assertGreaterEqual(self.elapsed('right','right'),1/60)
        self.assertGreaterEqual(self.elapsed('cw','cw'),1/60)
        self.assertGreaterEqual(self.elapsed('left_wall','left'),1/60)

    def test_opposite_key_and_other_actions_do_not_add_a_global_speed_limit(self):
        self.assertEqual(self.elapsed('left_wall','right'),0)
        self.assertEqual(self.elapsed('right','hard_drop'),0)

    def test_stop_during_neutral_frame_prevents_the_next_input(self):
        runner=self.runner('cw');runner.stopped.return_value=True
        with patch('pc_lab.live.time.perf_counter',return_value=100.0):
            with self.assertRaises(InterruptedError):runner.before_input('cw')
