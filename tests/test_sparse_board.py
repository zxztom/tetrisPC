import random,unittest
from pc_lab.blitz import board_cost
from pc_lab.engine import empty_board,lock,cells,fits


def reference_cost(board):
    heights=[max((y+1 for y in range(24) if board[y][x]!='_'),default=0) for x in range(10)]
    holes=sum(board[y][x]=='_' for x in range(10) for y in range(heights[x]))
    covered=sum(heights[x]-y for x in range(10) for y in range(heights[x]) if board[y][x]=='_')
    return (140*holes+10*covered+5*sum(abs(a-b) for a,b in zip(heights,heights[1:]))
            +2.5*sum(heights)+6*max(heights)+18*max(0,max(heights)-8)**2)


def reference_lock(board,points,piece):
    rows=[list(row) for row in board]
    for x,y in points:rows[y][x]=piece
    placed=tuple(''.join(row) for row in rows)
    cleared=tuple(y for y,row in enumerate(placed) if '_' not in row)
    after=tuple(row for y,row in enumerate(placed) if y not in cleared)+empty_board()[:len(cleared)]
    return after,placed,cleared


class SparseBoardTests(unittest.TestCase):
    def test_cost_exhaustive_cavities_and_random_full_height_boards(self):
        boards=[empty_board()]
        for mask in range(512):
            boards.append(tuple(''.join('X' if mask&(1<<(y*3+x)) else '_' for x in range(3))+'_______'
                                for y in range(3))+empty_board()[3:])
        rng=random.Random(367)
        for _ in range(500):
            boards.append(tuple(''.join(rng.choice('____IJLOSTZX') for x in range(10)) for y in range(24)))
        for board in boards:self.assertEqual(board_cost(board),reference_cost(board))

    def test_lock_matches_full_copy_with_multiline_clears_and_preexisting_full_rows(self):
        rng=random.Random(613);checked=0
        for _ in range(160):
            board=tuple(''.join(rng.choice('___X') for x in range(10)) for y in range(8))+empty_board()[8:]
            for piece in 'IJLOSTZ':
                for rotation in range(4):
                    for x in range(10):
                        y=21
                        while fits(board,cells(piece,rotation,x,y-1)):y-=1
                        points=cells(piece,rotation,x,y)
                        if fits(board,points):
                            self.assertEqual(lock(board,points,piece),reference_lock(board,points,piece));checked+=1
        quad=('XXXXXXXXX_',)*4+('XXXXXXXXXX',)+empty_board()[5:]
        points=((9,0),(9,1),(9,2),(9,3))
        self.assertEqual(lock(quad,points,'I'),reference_lock(quad,points,'I'))
        self.assertGreater(checked,20000)


if __name__=='__main__':unittest.main()
