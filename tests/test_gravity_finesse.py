import unittest
from unittest.mock import Mock

from pc_lab.blitz import Score
from pc_lab.blitz_live import BlitzRunner
from pc_lab.engine import empty_board,cells


class GravityFinesseTests(unittest.TestCase):
    def runner(self,level=1,profile='blitz'):
        runner=object.__new__(BlitzRunner)
        runner.finesse_policy='gravity';runner.allow180=True
        runner.score_state=Score(level=level);runner.simulation=profile
        return runner

    def test_actual_gravity_controls_budget_and_path_in_fixed_profiles(self):
        for level,profile,wanted in [(13,'blitz','balanced'),(14,'blitz','strict'),
                                     (1,'level15','strict'),(15,'level10','balanced'),(1,'20g','strict')]:
            with self.subTest(level=level,profile=profile):
                runner=self.runner(level,profile)
                self.assertEqual(runner.effective_finesse_policy(),wanted)
                self.assertEqual(runner.fault_allowance(),0 if wanted=='strict' else 999)
                self.assertEqual(runner.search_path_mode(),'ground180fine' if wanted=='strict' else 'ground180')

    def test_old_low_gravity_prefix_is_discarded_before_any_planning_at_20g(self):
        runner=self.runner(14)
        runner.prefix=[{'unexecutable_old_low_gravity_plan':True}]
        runner.planning_finesse_policy='balanced'
        runner.try_visible_setup_finish=Mock(side_effect=InterruptedError('probe boundary'))
        state=dict(board=empty_board(),hold=None,active='I',active_cells=cells('I',0,4,21))
        with self.assertRaisesRegex(InterruptedError,'probe boundary'):
            runner.choose(state,{},0,None)
        self.assertEqual(runner.prefix,[])
        self.assertEqual(runner.gravity_policy_switches,1)
        self.assertEqual(runner.planning_finesse_policy,'strict')

    def test_unchanged_gravity_keeps_known_plan(self):
        runner=self.runner(13);prefix=[{'known_plan':True}]
        runner.prefix=prefix;runner.planning_finesse_policy='balanced'
        runner.try_visible_setup_finish=Mock(side_effect=InterruptedError('probe boundary'))
        state=dict(board=empty_board(),hold=None,active='I',active_cells=cells('I',0,4,21))
        with self.assertRaises(InterruptedError):runner.choose(state,{},0,None)
        self.assertIs(runner.prefix,prefix)
