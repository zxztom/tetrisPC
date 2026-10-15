import importlib.util
import unittest
from pc_lab.solver import ROOT

spec=importlib.util.spec_from_file_location('native_timing_audit',ROOT/'scripts/audit-native-input-timing.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class NativeInputTimingTests(unittest.TestCase):
    def fixture(self):
        def event(frame,kind,key,subframe):
            return dict(frame=frame,type=kind,data=dict(key=key,subframe=subframe))
        replay=dict(replay=dict(options=dict(handling=dict(das=1.5)),events=[
            event(32,'keydown','moveLeft',.5),event(34,'keyup','moveLeft',.1),
            event(40,'keydown','softDrop',0),event(41,'keyup','softDrop',0),
            dict(frame=300,type='full',data=None)],
            results=dict(stats=dict(piecesplaced=8,finesse=dict(faults=0)))))
        session=dict(steps=[])
        pending=dict(input_timing=[dict(action='left',started=100,released=100.0085725)])
        return replay,session,pending

    def test_native_lifetime_can_cross_das_even_when_controller_tap_does_not(self):
        replay,session,pending=self.fixture()
        result=module.audit(replay,session,pending)
        self.assertTrue(result['key_sequences_identical'])
        self.assertEqual(result['native_key_presses'],1)
        self.assertEqual(len(result['direction_taps_crossing_das']),1)
        pair=result['direction_taps_crossing_das'][0]
        self.assertAlmostEqual(pair['native_ms'],26.6666666667)
        self.assertAlmostEqual(pair['controller_ms'],8.5725)
        self.assertFalse(result['reads_seed_or_future_queue'])

    def test_key_mismatch_does_not_pair_unrelated_timestamps(self):
        replay,session,pending=self.fixture()
        pending['input_timing'][0]['action']='right'
        result=module.audit(replay,session,pending)
        self.assertFalse(result['key_sequences_identical'])
        self.assertEqual(result['lifetime_pairs'],[])
        self.assertEqual(result['direction_taps_crossing_das'],[])
        self.assertEqual(result['sequence_mismatch'][0]['controller'],'moveRight')
