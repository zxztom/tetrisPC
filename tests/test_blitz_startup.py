import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from pc_lab.blitz_live import BlitzRunner
from pc_lab.engine import empty_board


class BlitzStartupTests(unittest.TestCase):
    def test_countdown_keeps_calibrated_roi_until_first_active_piece(self):
        runner=object.__new__(BlitzRunner)
        runner.hwnd=123
        runner.request={'start_timeout':1}
        runner.cancelled=lambda:False
        runner.hotkeys=Mock(pressed=threading.Event())
        runner.progress=Mock()
        runner.solver_warmed=True
        calibration=object()
        runner.geometry=calibration
        countdown=dict(active=None,hold=None,next='JLOTZI',board=empty_board())
        playing=dict(countdown,active='S',next='JLOTZ')
        image=Mock()
        observations=iter([countdown,playing])
        def observe(board):
            self.assertIs(runner.geometry,calibration)
            return next(observations),image
        runner.observe=observe
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent.parent/'output') as folder, \
             patch('pc_lab.windows.emergency_pressed',return_value=False), \
             patch('pc_lab.windows.user.GetForegroundWindow',return_value=123), \
             patch('pc_lab.blitz_live.time.sleep'):
            runner.folder=Path(folder)
            state,_=runner.initial_state()
        self.assertIs(state,playing)
        self.assertFalse(runner.waiting_for_start)

    def test_natural_lock_during_planning_prevents_hold_on_next_piece(self):
        original=dict(board=empty_board(),active='T',hold=None,next='JLOST')
        changed=[dict(original,active='J'),dict(original,hold='O'),
                 dict(original,next='LOSTZ'),
                 dict(original,board=('T_________',)+empty_board()[1:])]
        for actual in changed:
            with self.subTest(actual=actual):
                runner=object.__new__(BlitzRunner)
                runner.input_trace=[]
                runner.actual_gravity=lambda:20
                runner.observe=Mock(return_value=(actual,Mock()))
                runner.send=Mock()
                with self.assertRaisesRegex(RuntimeError,'Hold 前方块已变化'):
                    runner.ground_execute({'hold_used':True},original)
                runner.send.assert_not_called()
