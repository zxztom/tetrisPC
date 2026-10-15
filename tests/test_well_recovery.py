import unittest
from pc_lab.blitz import board_cost,score_move,Score
from pc_lab.engine import empty_board,load_kicks
from pc_lab.solver import ROOT


class WellRecoveryTests(unittest.TestCase):
    def test_keeps_one_quad_well_but_penalizes_two_independent_deep_wells(self):
        for x in (0,4,9):
            row='X'*x+'_'+'X'*(9-x);board=(row,)*8+empty_board()[8:]
            self.assertEqual(board_cost(board,True),board_cost(board))
        double=('_XXXXXXXX_',)*8+empty_board()[8:]
        self.assertGreater(board_cost(double,True)-board_cost(double),500)
        self.assertEqual(board_cost(empty_board(),True),0)

    def test_new_cost_preserves_known_hold_quad_pc(self):
        board=('XXXXXXXXX_',)*4+empty_board()[4:]
        step=score_move(board,'O','TLZSJ','I',load_kicks(ROOT/'data/srsplus90.properties'),Score(level=15),
                        allow180=True,allow_wall=True,budget=.03,multi_well=True)
        self.assertEqual(step['piece'],'I');self.assertTrue(step['hold_used'])
        self.assertEqual(len(step['cleared_rows']),4);self.assertEqual(step['board_after'],empty_board())


if __name__=='__main__':unittest.main()
