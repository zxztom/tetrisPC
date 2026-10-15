import unittest
from pc_lab.blitz_live import BlitzRunner
from pc_lab.blitz_validation import validate_blitz
from pc_lab.speed import speed_settings


class BlitzPulseTests(unittest.TestCase):
    def test_only_changes_local_blitz_pulse_preserving_unlimited_pacing_and_base_preset(self):
        r=object.__new__(BlitzRunner);r.request=dict(speed_preset='extreme',blitz_pulse_ms=1)
        r.timing=speed_settings('extreme')
        speed=r.speed()
        self.assertEqual(speed['tap_ms'],1);self.assertEqual(speed['target_pps'],0)
        self.assertEqual(speed['operation_interval_ms'],0);self.assertEqual(speed_settings('extreme')['tap_ms'],6)
        r.request={'finesse_policy':'balanced'};self.assertEqual(r.speed()['tap_ms'],6)

    def test_throughput_default_pairs_extreme_taps_without_changing_other_presets(self):
        r=object.__new__(BlitzRunner);r.request={};r.timing=speed_settings('extreme')
        self.assertEqual(r.speed()['tap_ms'],0)
        self.assertEqual(r.speed()['target_pps'],0)
        r.request={'blitz_pulse_ms':6};self.assertEqual(r.speed()['tap_ms'],6)
        r.request={};r.timing=speed_settings('sprint')
        self.assertEqual(r.speed()['tap_ms'],6)

    def test_invalid_pulses_fail_preflight(self):
        profile=dict(handling=dict(arr=0,sdf=41))
        for pulse in (True,-1,.1,25,float('nan'),float('inf'),'1'):
            with self.subTest(pulse=pulse),self.assertRaises(ValueError):
                validate_blitz(dict(speed_preset='extreme',blitz_pulse_ms=pulse),profile)
        with self.assertRaises(ValueError):validate_blitz(dict(speed_preset='sprint',blitz_pulse_ms=1),profile)
        self.assertEqual(validate_blitz(dict(speed_preset='extreme',blitz_pulse_ms=1),profile),(120,0))
        self.assertEqual(validate_blitz(dict(speed_preset='extreme',blitz_pulse_ms=0),profile),(120,0))


if __name__=='__main__':unittest.main()
