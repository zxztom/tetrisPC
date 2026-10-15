import random,unittest
from pc_lab.ground_geometry import GroundGeometry
from pc_lab.blitz import _ground_locks_uncached,I_180,JLSTZ_180
from pc_lab.engine import empty_board,cells,fits,load_kicks
from pc_lab.solver import ROOT


class GroundGeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.kicks=load_kicks(ROOT/'data/srsplus90.properties')

    def test_packed_collision_agrees_at_walls_ceiling_and_cavities(self):
        rng=random.Random(713)
        for _ in range(12):
            board=tuple(''.join(rng.choice('___IJLOSTZX') for x in range(10)) for y in range(24))
            for piece in 'IJLOSTZ':
                geo=GroundGeometry(board,piece,self.kicks,I_180 if piece=='I' else JLSTZ_180)
                for r in range(4):
                    for y in range(-3,27):
                        for x in range(-3,13):
                            self.assertEqual(geo.fits(x,y,r),fits(board,cells(piece,r,x,y)),(piece,x,y,r))

    def test_complete_routes_spins_and_limits_match_cell_based_generator(self):
        rng=random.Random(1903)
        boards=[empty_board(),('_SSIIIIJJJ','_TSSSS_J__','___OO____L')+empty_board()[3:],
                ('LL_SSSSZZI','LL__SSSSZI','LL_______I')+empty_board()[3:]]
        boards.extend(tuple(''.join(rng.choice('____X') for x in range(10)) for y in range(6))+empty_board()[6:]
                      for _ in range(22))
        for board in boards:
            for piece in 'IJLOSTZ':
                for options in ({},{'allow180':True,'allow_wall':True},
                                {'allow180':True,'allow_wall':True,'max_cost':2,'max_inputs':2}):
                    fast=_ground_locks_uncached(board,piece,self.kicks,**options)
                    slow=_ground_locks_uncached(board,piece,self.kicks,fast_geometry=False,**options)
                    self.assertEqual(fast,slow,(piece,board[:6],options))
                if fast:
                    target=next(iter(fast))
                    for spin in (None,'full','mini'):
                        options=dict(wanted=target,wanted_spin=spin,allow180=True,allow_wall=True)
                        self.assertEqual(_ground_locks_uncached(board,piece,self.kicks,**options),
                            _ground_locks_uncached(board,piece,self.kicks,fast_geometry=False,**options))


if __name__=='__main__':unittest.main()
