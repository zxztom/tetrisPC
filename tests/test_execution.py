import os
import unittest
from pathlib import Path
from unittest.mock import Mock,MagicMock,patch

from pc_lab.engine import empty_board


@unittest.skipUnless(os.name=='nt','Windows executor')
class ExecutionTests(unittest.TestCase):
    def test_only_one_executor_can_own_desktop_input(self):
        from pc_lab.live import Runner
        with patch('pc_lab.live.connect_game',return_value={'hwnd':42}):
            first=Runner({})
            try:
                with self.assertRaisesRegex(RuntimeError,'已有桌面操作任务'):Runner({})
            finally:first.control_lock.close()
            third=Runner({});third.control_lock.close()
    def make_runner(self):
        from pc_lab.live import Runner
        runner=Runner.__new__(Runner)
        runner.folder=MagicMock()
        runner.send=Mock()
        return runner

    def test_missed_input_retries_only_after_unchanged_pose_observation(self):
        runner=self.make_runner()
        runner.wait_for=Mock(side_effect=[RuntimeError('timeout'),None])
        previous=((3,21),(4,21),(5,21),(6,21))
        target=tuple((x+1,y) for x,y in previous)
        runner.observe=Mock(return_value=({'board':empty_board(),'active_cells':previous},None))
        runner.verify_movement('right',previous,target,empty_board())
        runner.send.assert_called_once_with('right')

    def test_unexpected_movement_is_not_repeated(self):
        runner=self.make_runner()
        runner.wait_for=Mock(side_effect=RuntimeError('timeout'))
        previous=((3,21),(4,21),(5,21),(6,21))
        target=tuple((x+1,y) for x,y in previous)
        wrong=tuple((x+2,y) for x,y in previous)
        runner.observe=Mock(return_value=({'board':empty_board(),'active_cells':wrong},None))
        with self.assertRaises(RuntimeError):runner.verify_movement('right',previous,target,empty_board())
        runner.send.assert_not_called()

    def test_pc_banner_overlay_waits_without_repeating_successful_input(self):
        runner=self.make_runner()
        previous=((3,21),(4,21),(5,21),(6,21))
        target=tuple((x+1,y) for x,y in previous)
        overlay={'board':('XX________',)+empty_board()[1:],'active_cells':list(target)+[(0,0),(1,0)]}
        clean={'board':empty_board(),'active_cells':target}
        runner.observe=Mock(return_value=(overlay,None))
        runner.wait_for=Mock(side_effect=[RuntimeError('banner'),(clean,None)])
        runner.verify_movement('right',previous,target,empty_board())
        runner.send.assert_not_called()

    def test_automatic_retry_is_bounded_and_only_for_planning_failure(self):
        from pc_lab.live import run_live,PlanningFailure
        runner=Mock(folder=Path('failed-attempt'),completed_cycles=0,completed_pcs=0,steps=[])
        runner.latest=None
        runner.stopped.return_value=False
        runner.run.side_effect=PlanningFailure('no route')
        with patch('pc_lab.live.Runner',return_value=runner) as factory:
            with self.assertRaises(PlanningFailure):
                run_live({'auto_retry':True,'max_retries':2})
        self.assertEqual(factory.call_count,3)
        runner.run.side_effect=RuntimeError('unexpected pose')
        with patch('pc_lab.live.Runner',return_value=runner) as factory:
            with self.assertRaises(RuntimeError):run_live({'auto_retry':True,'max_retries':2})
        self.assertEqual(factory.call_count,1)

    def test_operation_interval_limits_and_changes_are_respected(self):
        runner=self.make_runner();runner.timing={'operation_interval_ms':50};runner.input_released=0
        runner.stopped=Mock(return_value=False)
        with patch('pc_lab.live.time.perf_counter',side_effect=[.01,.03,.05]),patch('pc_lab.live.time.sleep') as sleep:
            runner.before_input()
        self.assertEqual(sleep.call_count,2)
        runner.timing['operation_interval_ms']=100
        with patch('pc_lab.live.time.perf_counter',side_effect=[.06,.10]),patch('pc_lab.live.time.sleep') as sleep:
            runner.before_input()
        self.assertEqual(sleep.call_count,1)
        for value in (-1,2001,float('nan'),float('inf')):
            runner.timing['operation_interval_ms']=value
            with self.assertRaises(ValueError):runner.interval_ms()

    def test_zen_planning_failure_stops_without_retrying_or_resetting(self):
        from pc_lab.live import run_live,PlanningFailure
        runner=Mock(latest={'game_mode':'zen'})
        runner.run.side_effect=PlanningFailure('no continuation')
        with patch('pc_lab.live.Runner',return_value=runner) as factory:
            with self.assertRaisesRegex(PlanningFailure,'不会自动重开'):
                run_live({'auto_retry':True,'max_retries':3})
        self.assertEqual(factory.call_count,1)
        runner.write_status.assert_called_once_with('error','ZEN 当前无法继续 PC，已停止并保留进度；不会自动重开。')

    def test_opt_in_zen_recovery_is_bounded_in_a_test_and_preserves_failure_history(self):
        from pc_lab.live import run_live,PlanningFailure
        failed=Mock(folder=Path('failed'),completed_cycles=0,completed_pcs=2,steps=[{},{}],latest={'game_mode':'zen'})
        failed.stopped.return_value=False;failed.run.side_effect=PlanningFailure('no continuation')
        successful=Mock(folder=MagicMock());successful.run.return_value={'status':'done'}
        with patch('pc_lab.live.Runner',side_effect=[failed,successful]) as factory:
            result=run_live({'recover_on_failure':True,'max_retries':1})
        self.assertEqual(result['recovery_count'],1)
        self.assertEqual(result['previous_attempts'][0]['completed_pcs'],2)
        self.assertTrue(factory.call_args_list[1].args[0]['restart'])

    def test_unlimited_recovery_still_obeys_cancellation(self):
        from pc_lab.live import run_live,PlanningFailure
        runner=Mock(latest={'game_mode':'zen'});runner.run.side_effect=PlanningFailure('no continuation')
        with patch('pc_lab.live.Runner',return_value=runner) as factory:
            with self.assertRaises(PlanningFailure):run_live({'recover_on_failure':True,'max_retries':0},cancelled=lambda:True)
        self.assertEqual(factory.call_count,1)

    def test_instant_drop_tuck_is_verified_before_hard_drop(self):
        from pc_lab.engine import cells,load_kicks
        from pc_lab.solver import ROOT
        runner=self.make_runner();runner.timing={'operation_interval_ms':20}
        runner.kicks=load_kicks(ROOT/'data/srsplus90.properties')
        board=empty_board();target=cells('I',0,2,0)
        step={'cells':target,'execution_progress':[]}
        actual={'board':board,'active':'I','next':'JLOST','active_cells':target}
        def verify(predicate,*args,**kwargs):
            self.assertTrue(predicate(actual))
            self.assertEqual(runner.send.call_args_list[-1].args[0],'left')
            return actual,None
        runner.wait_for=Mock(side_effect=verify)
        result=runner.tuck_suffix(board,'I',(4,19,0),{'actions':['soft_drop','left','left','hard_drop']},step,'JLOST')
        self.assertEqual(result,['soft_drop','left','left','hard_drop'])
        self.assertEqual([c.args[0] for c in runner.send.call_args_list],['down','left','left','hard_drop'])

    def test_failed_tuck_check_does_not_send_hard_drop(self):
        runner=self.make_runner();runner.timing={'operation_interval_ms':20};runner.fall_rate=1
        from pc_lab.engine import cells,load_kicks
        from pc_lab.solver import ROOT
        runner.kicks=load_kicks(ROOT/'data/srsplus90.properties')
        runner.latest={'next':'JLOST'};runner.wait_for=Mock(side_effect=RuntimeError('pose wrong'))
        with self.assertRaises(RuntimeError):
            runner.tuck_suffix(empty_board(),'I',(4,19,0),{'actions':['soft_drop','left','hard_drop']},
                               {'cells':cells('I',0,3,0),'execution_progress':[]},'JLOST')
        self.assertNotIn('hard_drop',[c.args[0] for c in runner.send.call_args_list])

    def test_waiting_does_not_capture_another_foreground_window(self):
        runner=self.make_runner()
        runner.request={'wait_start':True};runner.hwnd=42;runner.progress=Mock()
        runner.cancelled=Mock(side_effect=[False,True]);runner.observe=Mock()
        with patch('pc_lab.live.emergency_pressed',return_value=False), \
             patch('pc_lab.live.user.GetForegroundWindow',return_value=43), \
             patch('pc_lab.live.time.sleep'):
            with self.assertRaises(InterruptedError):runner.initial_state()
        runner.observe.assert_not_called()

    def test_focus_loss_stops_play_but_leaves_waiting_armed(self):
        runner=self.make_runner();runner.hwnd=42;runner.cancelled=Mock(return_value=False)
        with patch('pc_lab.live.emergency_pressed',return_value=False), \
             patch('pc_lab.live.user.GetForegroundWindow',return_value=43):
            runner.waiting_for_start=True;self.assertFalse(runner.stopped())
            runner.waiting_for_start=False;self.assertTrue(runner.stopped())


if __name__=='__main__':unittest.main()
