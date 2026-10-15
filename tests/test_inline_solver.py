import unittest
from pathlib import Path
from unittest.mock import patch
from pc_lab.fast_solver import find_pc
from pc_lab.search_worker import close_worker,search
from pc_lab.solver import ROOT


class InlineSolverTests(unittest.TestCase):
    def test_inline_and_saved_fields_have_identical_independently_verified_plans(self):
        try:
            args=dict(rows=['I_________','IT________','ITTSS_____','ITSS______'],hold='Z',lines=4,
                      mode='soft',path_mode='ground180fine',persistent=True,timeout=1.5,
                      kick_path=ROOT/'data/srsplus90.properties')
            saved=find_pc('JLOSLTJ',save=True,**args)
            with patch('pc_lab.fast_solver.Path.mkdir',side_effect=AssertionError('must not create a search folder')), \
                 patch('pc_lab.fast_solver.Path.write_text',side_effect=AssertionError('must not write a field or log')):
                inline=find_pc('JLOSLTJ',save=False,**args)
            self.assertEqual(saved['status'],'solved')
            self.assertEqual(saved['steps'],inline['steps'])
            self.assertEqual(saved['initial_board'],inline['initial_board'])
            self.assertIsNone(inline['output_directory'])
            folder=Path(saved['output_directory'])
            self.assertTrue((folder/'field.txt').is_file())
            self.assertTrue((folder/'result.json').is_file())
        finally:close_worker()

    def test_invalid_inline_field_is_rejected_and_next_request_is_clean(self):
        args=['inline:'+('_'*19),'O','2','ground180fine','avoid',str(ROOT/'data/srsplus90.properties')]
        try:
            out,code=search(args,1,lambda:False)
            self.assertEqual(code,2);self.assertIn('SEARCH_ERROR',out)
            args[0]='inline:__XXXXXXXX__XXXXXXXX'
            out,code=search(args,1,lambda:False)
            self.assertEqual(code,0);self.assertIn('SOLUTION ',out)
        finally:close_worker()
