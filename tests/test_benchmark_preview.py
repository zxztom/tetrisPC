"""The offline oracle must expose exactly the selected visible preview."""
import importlib.util
import unittest
from unittest.mock import patch

from pc_lab.engine import cells, lock
from pc_lab.solver import ROOT

spec = importlib.util.spec_from_file_location('visible_benchmark', ROOT/'scripts/benchmark-blitz-visible.py')
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class BenchmarkPreviewTests(unittest.TestCase):
    def check_preview(self, count):
        queue = 'OIJLSTZ' * 3

        def choose(runner, state, known, current, held_source):
            self.assertEqual(state['next'], queue[1:1+count])
            self.assertEqual(known, {i: queue[i] for i in range(count+1)})
            self.assertEqual(current, 0)
            self.assertIsNone(held_source)
            target = cells('O', 0, 4, 0)
            board, _, cleared = lock(state['board'], target, 'O')
            return dict(piece='O', hold_used=False, cells=target, board_after=board,
                        cleared_rows=cleared, hold_after=None, spin='none',
                        queue_index_before=0, queue_index_after=1)

        with patch.object(benchmark.BlitzRunner, 'choose', choose):
            result = benchmark.simulate(queue, 'balanced', 'dpc', 1, next_count=count)
        self.assertIsNone(result['error'])
        self.assertEqual(result['pieces'], 1)
        self.assertEqual(result['preview_count'], count)

    def test_five_next_does_not_expose_seventh_source(self):
        self.check_preview(5)

    def test_six_next_exposes_seventh_source(self):
        self.check_preview(6)
