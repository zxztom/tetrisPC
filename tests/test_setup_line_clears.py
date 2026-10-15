import unittest
from unittest.mock import patch
from pc_lab.best_fields import fields,field_setups
from pc_lab.engine import empty_board,load_kicks,lock,cells
from pc_lab.blitz import settle,ground_action
from pc_lab.finesse import estimated_faults
from pc_lab.solver import ROOT


class SetupLineClearTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.kicks=load_kicks(ROOT/'data/srsplus90.properties')

    def template(self,phase,signature):
        return next(f for f in fields() if f['phase']==phase and f['signature']==signature)

    def test_four_piece_setup_can_clear_one_line_and_keep_verified_three_row_goal(self):
        # Legal bag boundary: previous bag's held I, then a fresh IOSJTZL.
        # Four placements use the two I plus O and S, retaining actual J.
        known={20:'I',**{21+i:p for i,p in enumerate('IOSJTZL')}}
        with patch('pc_lab.best_fields.fields',return_value=[self.template(3,'IISO')]):
            plans=field_setups(known,21,20,3,self.kicks,path_mode='ground180fine',prefer_finesse=True)
        self.assertTrue(plans);plan=plans[0];board=empty_board()
        for step in plan:
            self.assertEqual(tuple(step['board_before']),board)
            pose=settle(board,step['piece'],(4,21,0))
            for action in step['actions'][:-1]:pose=ground_action(board,step['piece'],pose,action,self.kicks)
            self.assertEqual(tuple(sorted(cells(step['piece'],pose[2],pose[0],pose[1]))),tuple(step['cells']))
            board,_,cleared=lock(board,step['cells'],step['piece'])
            self.assertEqual(tuple(step['board_after']),board)
            self.assertEqual(tuple(step['cleared_rows']),cleared)
        self.assertEqual(len(plan),4)
        self.assertEqual(sum(len(s['cleared_rows']) for s in plan),1)
        self.assertEqual(sum(c!='_' for row in board for c in row),6)
        self.assertEqual(sum(estimated_faults(s['piece'],s['cells'],s['actions']) for s in plan),0)
        self.assertEqual(plan[0]['source_setup_cleared_lines'],1)

    def test_public_100_percent_field_does_not_bypass_ground_reachability(self):
        known={0:'T',**{5+i:p for i,p in enumerate('IOOIJL')}}
        with patch('pc_lab.best_fields.fields',return_value=[self.template(5,'IIOO')]):
            air=field_setups(known,5,0,5,self.kicks,path_mode='hard')
            ground=field_setups(known,5,0,5,self.kicks,path_mode='ground180fine')
        self.assertTrue(air)
        self.assertEqual(air[0][0]['source_reported_coverage'],100)
        self.assertEqual(sum(len(s['cleared_rows']) for s in air[0]),1)
        self.assertEqual(ground,[])

    def test_clear_during_setup_leaves_six_pieces_for_a_real_four_line_pc(self):
        from pc_lab.fast_solver import find_pc
        from pc_lab.search_worker import close_worker
        # Finite regression only: held I plus IOSJTZL, next bag starts JLO.
        known={20:'I',**{21+i:p for i,p in enumerate('IOSJTZL')}}
        with patch('pc_lab.best_fields.fields',return_value=[self.template(3,'IISO')]):
            setup=field_setups(known,21,20,3,self.kicks,path_mode='ground180fine')[0]
        try:
            finish=find_pc('TZLJLO',hold=setup[-1]['hold_after'],
                rows=list(reversed(setup[-1]['board_after'][:3])),lines=3,mode='soft',
                path_mode='ground180fine',persistent=True,timeout=1.5,
                kick_path=ROOT/'data/srsplus90.properties',save=False)
            self.assertEqual(finish['status'],'solved')
            self.assertEqual(len(setup)+len(finish['steps']),10)
            self.assertEqual(sum(len(s['cleared_rows']) for s in setup+finish['steps']),4)
            self.assertEqual(tuple(finish['steps'][-1]['board_after']),empty_board())
            self.assertEqual(sum(estimated_faults(s['piece'],s['cells'],s['actions']) for s in setup+finish['steps']),0)
        finally:close_worker()
