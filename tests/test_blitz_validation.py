import unittest
from unittest.mock import patch
from pc_lab.blitz_validation import validate_blitz


class BlitzValidationTests(unittest.TestCase):
    def profile(self,arr=0,sdf=41):
        return dict(handling=dict(arr=arr,sdf=sdf))

    def request(self,**kw):
        return dict(cycle_mode='blitz',speed_preset='extreme',**kw)

    def test_extreme_preserves_unlimited_pacing_and_complete_game(self):
        self.assertEqual(validate_blitz(self.request(),self.profile()),(120,0))
        self.assertEqual(validate_blitz(self.request(blitz_strategy='score'),self.profile()),(120,0))
        self.assertEqual(validate_blitz(self.request(blitz_seconds=30,max_pieces=35),self.profile()),(30,35))

    def test_invalid_configuration_and_request_rejected(self):
        bad=[dict(seed='anything'),dict(live_mode='seeded'),dict(rotation_rules='SRS'),
             dict(simulation_profile='other'),dict(blitz_strategy='other'),dict(finesse_policy='other'),
             dict(blitz_seconds=float('nan')),dict(blitz_seconds=121),dict(max_pieces=True),
             dict(max_pieces=3.5),dict(max_pieces=2001),dict(operation_interval_ms=41),
             dict(setup_finesse_weight=float('inf')),dict(setup_finesse_weight=-1)]
        for options in bad:
            with self.subTest(options=options),self.assertRaises(ValueError):
                validate_blitz(self.request(**options),self.profile())
        for profile in (None,self.profile(sdf=40)):
            with self.assertRaises(ValueError):validate_blitz(self.request(),profile)
        with self.assertRaises(ValueError):
            validate_blitz(self.request(finesse_policy='strict'),self.profile(arr=1))
        self.assertEqual(validate_blitz(self.request(finesse_policy='gravity'),self.profile()),(120,0))
        with self.assertRaises(ValueError):
            validate_blitz(self.request(finesse_policy='gravity'),self.profile(arr=1))

    def test_farm_rejects_before_loading_navigation_or_connecting(self):
        from pc_lab.farm_live import run_farm
        with patch('pc_lab.config.load_profile',return_value=self.profile(sdf=40)), \
             patch('pc_lab.farm_navigation.NativeNavigator.load_recipe') as recipe, \
             patch('pc_lab.windows.find_game') as connect,patch('pc_lab.windows.focus') as focus:
            with self.assertRaises(ValueError):run_farm(self.request())
        recipe.assert_not_called();connect.assert_not_called();focus.assert_not_called()

    def test_single_game_rejects_before_runner_constructor(self):
        from pc_lab.blitz_live import BlitzRunner
        with patch('pc_lab.config.load_profile',return_value=self.profile()), \
             patch('pc_lab.live.Runner.__init__') as connect:
            with self.assertRaises(ValueError):BlitzRunner(self.request(rotation_rules='SRS'))
        connect.assert_not_called()
