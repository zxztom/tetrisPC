import unittest
from unittest.mock import patch
from pc_lab.online import choose_plan,all_placements_observed
from pc_lab.fast_solver import find_pc
from pc_lab.engine import empty_board,board_from_rows
from pc_lab.search_worker import close_worker
from pc_lab.solver import ROOT


class ObservedFinishTests(unittest.TestCase):
    def test_seven_locked_pieces_known_even_when_final_carry_is_not(self):
        # Actual visible information before native piece 4 of the old
        # 680-piece run. The first three locked pieces are L, O and J;
        # source 0 T is held, and sources 4..9 are the six visible pieces.
        rows=['_______JJJ','_________J','_______LOO','_____LLLOO']
        known={0:'T',**{4+i:p for i,p in enumerate('IZSJZL')}}
        try:
            result=find_pc('IZSJZL',rows=rows,hold='T',lines=4,mode='soft',
                path_mode='ground180fine',persistent=True,timeout=1.5,
                kick_path=ROOT/'data/srsplus90.properties',save=False)
            self.assertEqual(result['status'],'solved')
            self.assertEqual(result['final_hold'],'?')
            self.assertTrue(all_placements_observed(result['steps'],known,4,0,35))
            stats=dict(probes=0,plans=0,incomplete=0)
            with patch('pc_lab.online.find_pc',return_value=result) as solver, \
                 patch('pc_lab.online.complete_bags',side_effect=AssertionError('must not predict a piece')):
                plan=choose_plan(known,4,0,board_from_rows(rows),4,35,
                    path_mode='ground180fine',observed_finish_first=True,visible_finish_stats=stats,time_budget=.095)
            self.assertEqual(solver.call_args.args[0],'IZSJZL')
            self.assertEqual(len(plan),7)
            self.assertTrue(all(s['observed_finish'] and not s['future_was_unknown'] for s in plan))
            self.assertTrue(plan[-1]['unknown_carry'])
            self.assertEqual(tuple(plan[-1]['board_after']),empty_board())
            self.assertEqual(stats,dict(probes=1,plans=1,incomplete=0))
        finally:close_worker()

    def test_unknown_locked_piece_or_cycle_overrun_is_rejected(self):
        known={0:'O',1:'I'}
        plan=[dict(piece='O',queue_index_before=0,hold_used=False),dict(piece='J',queue_index_before=1,hold_used=True)]
        self.assertFalse(all_placements_observed(plan,known,0,None,35))
        self.assertFalse(all_placements_observed([dict(piece='I',queue_index_before=0,hold_used=False)],known,1,None,1))
        self.assertFalse(all_placements_observed([dict(piece='O',queue_index_before=0,hold_used=True)],known,1,0,35,False))

    def test_incomplete_probe_falls_back_to_forecast_without_claiming_known_finish(self):
        known={0:'Z',**{1+i:p for i,p in enumerate('IJLOST')}}
        board=('OOOO______','OOOO______','O_________','OOO_______')+empty_board()[4:]
        # Twelve occupied cells leave seven placements. The finite probe
        # is incomplete; a forecast still offers an observed first move.
        step=dict(piece='I',hold_used=False,cells=[(0,0),(1,0),(2,0),(3,0)],actions=['hard_drop'])
        stats=dict(probes=0,plans=0,incomplete=0)
        with patch('pc_lab.online.find_pc',side_effect=[dict(status='incomplete'),dict(status='solved',steps=[step])]):
            plan=choose_plan(known,1,0,board,4,35,samples=1,observed_finish_first=True,visible_finish_stats=stats,time_budget=1)
        self.assertEqual(stats,dict(probes=1,plans=0,incomplete=1))
        self.assertTrue(plan[0]['future_was_unknown'])
        self.assertNotIn('observed_finish',plan[0])
