import unittest
from unittest.mock import patch
from pc_lab.blitz_live import BlitzRunner
from pc_lab.blitz import Score,score_move
from pc_lab.engine import empty_board,load_kicks,reachable_locks,reconstruct
from pc_lab.fast_solver import find_pc
from pc_lab.search_worker import close_worker
from pc_lab.solver import ROOT


class ThroughputTests(unittest.TestCase):
    def test_plain_policy_removes_reference_fault_budget_but_keeps_geometry(self):
        r=object.__new__(BlitzRunner);r.finesse_policy='throughput';r.allow180=True
        self.assertFalse(r.standard_inputs_only());self.assertEqual(r.fault_allowance(),999)
        self.assertEqual(r.search_path_mode(),'ground180plain')
        kicks=load_kicks(ROOT/'data/srsplus90.properties')
        self.assertEqual(reachable_locks(empty_board(),'T',kicks,'ground180plain'),
                         reachable_locks(empty_board(),'T',kicks,'ground180'))
        r.finesse_policy='balanced';self.assertEqual(r.search_path_mode(),'ground180')
        r.finesse_policy='strict';self.assertEqual(r.search_path_mode(),'ground180fine')

    def test_plain_search_independently_validates_pc_without_fine_order_pass(self):
        from pc_lab import search_worker
        original=search_worker.search;outputs=[]
        def search(*args,**kwargs):
            output,code=original(*args,**kwargs);outputs.append(output);return output,code
        try:
            with patch('pc_lab.fast_solver.reconstruct',wraps=reconstruct) as validate, \
                 patch('pc_lab.search_worker.search',side_effect=search):
                result=find_pc('JLOSTZIJLO',lines=4,mode='soft',path_mode='ground180plain',
                    timeout=2,persistent=True,save=False,kick_path=ROOT/'data/srsplus90.properties')
            self.assertEqual(result['status'],'solved')
            self.assertEqual(tuple(result['steps'][-1]['board_after']),empty_board())
            self.assertTrue(validate.called)
            self.assertTrue(all('fine' not in c.args[6] for c in validate.call_args_list))
            self.assertTrue(all(not s['finesse_standard_finish'] for s in result['steps']))
            self.assertTrue(all('FINESSE_SEARCH' not in output for output in outputs))
        finally:close_worker()

    def test_survival_can_remove_fault_bias_without_changing_default(self):
        first=tuple((x,0) for x in range(4));second=tuple((x,0) for x in range(6,10))
        route=dict(actions=['left','hard_drop'],spin='none',x=0,y=0,rotation='0')
        kicks=load_kicks(ROOT/'data/srsplus90.properties')
        with patch('pc_lab.blitz.ground_locks',return_value={first:route,second:route}), \
             patch('pc_lab.blitz.board_cost',return_value=0), \
             patch('pc_lab.finesse.estimated_faults',side_effect=lambda p,points,a:int(points==first)):
            old=score_move(empty_board(),'I','',None,kicks,Score(),hold_available=False,budget=0)
            new=score_move(empty_board(),'I','',None,kicks,Score(),hold_available=False,budget=0,fault_penalty=0)
        self.assertEqual(tuple(old['cells']),second)
        self.assertEqual(tuple(new['cells']),first)


if __name__=='__main__':unittest.main()
