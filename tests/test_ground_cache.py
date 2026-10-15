import unittest
from pc_lab.blitz import (ground_locks,_ground_locks_uncached,clear_ground_cache,ground_cache_info)
from pc_lab.engine import empty_board,load_kicks,cells
from pc_lab.solver import ROOT


class GroundCacheTests(unittest.TestCase):
    def setUp(self):
        self.kicks=load_kicks(ROOT/'data/srsplus90.properties')
        clear_ground_cache()

    def test_cached_routes_retain_exact_paths_spins_and_all_constraints(self):
        boards=[empty_board(),('_SSIIIIJJJ','_TSSSS_J__','___OO____L')+empty_board()[3:]]
        for board in boards:
            for piece in 'IJLOSTZ':
                for options in ({},{'allow180':True,'allow_wall':True},
                                {'max_inputs':1,'max_cost':1,'allow_wall':True}):
                    expected=_ground_locks_uncached(board,piece,self.kicks,**options)
                    self.assertEqual(ground_locks(board,piece,self.kicks,**options),expected)
                    self.assertEqual(ground_locks(board,piece,self.kicks,**options),expected)
                    if expected:
                        target=next(iter(expected))
                        for spin in (None,'none','mini','full'):
                            query=dict(options,wanted=target,wanted_spin=spin)
                            self.assertEqual(ground_locks(board,piece,self.kicks,**query),
                                _ground_locks_uncached(board,piece,self.kicks,**query))

    def test_caller_mutation_and_changed_kick_contents_cannot_poison_cache(self):
        board=empty_board();wanted=tuple(sorted(cells('J',1,0,1)))
        query=dict(wanted=wanted,allow180=True,allow_wall=True)
        original=ground_locks(board,'J',self.kicks,**query)
        poisoned=ground_locks(board,'J',self.kicks,**query)
        self.assertTrue(poisoned)
        poisoned[wanted]['actions'].append('bad');poisoned[wanted]['spin']='full'
        self.assertEqual(ground_locks(board,'J',self.kicks,**query),original)
        misses=ground_cache_info()['misses']
        self.kicks['J.NE']=((50,50),)
        changed=ground_locks(board,'J',self.kicks,**query)
        self.assertEqual(ground_cache_info()['misses'],misses+1)
        self.assertEqual(changed,_ground_locks_uncached(board,'J',self.kicks,**query))

    def test_actual_start_pose_and_cache_bound(self):
        board=empty_board();wanted=tuple(sorted(cells('O',0,0,0)))
        self.assertEqual(ground_locks(board,'O',self.kicks,wanted=wanted,max_inputs=0),{})
        actual=ground_locks(board,'O',self.kicks,start=(0,0,0),wanted=wanted,max_inputs=0)
        self.assertEqual(actual[wanted]['actions'],['hard_drop'])
        misses=ground_cache_info()['misses']
        self.assertEqual(ground_locks(board,'O',self.kicks,start=(0,21,0),wanted=wanted,max_inputs=0),actual)
        self.assertEqual(ground_cache_info()['misses'],misses)
        for limit in range(520):ground_locks(board,'O',self.kicks,max_inputs=0,max_cost=limit)
        self.assertEqual(ground_cache_info()['currsize'],512)


if __name__=='__main__':unittest.main()
