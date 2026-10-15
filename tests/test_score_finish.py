import json,unittest
from pc_lab.blitz import Score,settle,ground_action
from pc_lab.blitz_finish import improve_finish
from pc_lab.engine import empty_board,load_kicks,cells,lock
from pc_lab.finesse import estimated_faults
from pc_lab.solver import ROOT


class ScoreFinishTests(unittest.TestCase):
    def setUp(self):
        self.case=json.loads((ROOT/'data/score-finish-regression.json').read_text(encoding='utf-8'))
        self.kicks=load_kicks(ROOT/'data/srsplus90.properties')
        incumbent=[dict(s,board_before=tuple(s['board_before']),board_after=tuple(s['board_after'])) for s in self.case['incumbent']]
        self.options=dict(board=tuple(self.case['board']),queue=self.case['queue'],held=self.case['held'],
            kicks=self.kicks,score=Score(**self.case['score']),lines=self.case['lines'],incumbent=incumbent,budget=.5)

    def verify(self,plan):
        board=self.options['board'];score=self.options['score'];faults=0
        for step in plan:
            target=tuple(sorted(map(tuple,step['cells'])))
            pose=settle(board,step['piece'],(4,21,0))
            for action in step['actions'][:-1]:pose=ground_action(board,step['piece'],pose,action,self.kicks)
            self.assertEqual(tuple(sorted(cells(step['piece'],pose[2],pose[0],pose[1]))),target)
            board,_,clears=lock(board,target,step['piece'])
            self.assertEqual(board,tuple(step['board_after']))
            self.assertEqual(clears,tuple(step['cleared_rows']))
            score=score.place(len(clears),step.get('spin','none'),board==empty_board())
            faults+=estimated_faults(step['piece'],target,step['actions'])
        self.assertEqual(board,empty_board())
        return score.score,faults

    def test_score_objective_can_choose_higher_scoring_real_pc_geometry(self):
        usual=self.verify(improve_finish(**self.options))
        higher=self.verify(improve_finish(**self.options,score_first=True))
        self.assertEqual(usual[1],0)
        self.assertGreater(higher[0],usual[0])

    def test_score_objective_respects_zero_fault_budget_including_last_move(self):
        score,faults=self.verify(improve_finish(**self.options,score_first=True,max_faults=0))
        self.assertEqual(faults,0)
        self.assertGreaterEqual(score,self.case['standard']['score'])

    def test_expired_score_search_keeps_independently_verified_incumbent(self):
        self.options['budget']=0
        self.assertIs(improve_finish(**self.options,score_first=True,max_faults=0),self.options['incumbent'])


if __name__=='__main__':unittest.main()
