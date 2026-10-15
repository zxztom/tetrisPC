import unittest

from pc_lab.engine import (board_from_rows, canonicalize, cells, empty_board,
                           load_kicks, lock, queue_choices, reachable_locks)
from pc_lab.solver import KICKS, normalize_queue


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kicks = load_kicks(KICKS)

    def test_solver_coordinate_convention_for_i_and_o(self):
        self.assertEqual(set(cells("I", 0, 4, 0)), {(3, 0), (4, 0), (5, 0), (6, 0)})
        self.assertEqual(set(cells("I", 1, 4, 2)), {(4, 3), (4, 2), (4, 1), (4, 0)})
        self.assertEqual(self.kicks["I.NE"][0], (1, 0))
        before = set(cells("O", 0, 4, 20))
        self.assertEqual(set(cells("O", 1, 4, 21)), before)

    def test_line_clear_collapses_upper_blocks(self):
        board = board_from_rows(["X_________", "__________", "XXXXXXXX__", "XXXXXXXX__"])
        after, placed, cleared = lock(board, cells("O", 0, 8, 0), "O")
        self.assertEqual(cleared, (0, 1))
        self.assertEqual(after[1], "X_________")
        self.assertEqual(after[0], "__________")
        self.assertEqual(placed[0], "XXXXXXXXOO")
        self.assertEqual(sum(c != "_" for row in after for c in row), 1)

    def test_hold_is_a_single_slot_not_arbitrary_reordering(self):
        self.assertEqual(list(queue_choices("TJLO", 0, None, True)),
                         [("T", 1, None, False), ("J", 2, "T", True)])
        self.assertEqual(list(queue_choices("TJLO", 2, "T", True)),
                         [("L", 3, "T", False), ("T", 3, "L", True)])
        self.assertEqual(list(queue_choices("TJLO", 0, "I", False)), [("T", 1, "I", False)])

    def test_unknown_preview_is_never_placed(self):
        self.assertEqual(list(queue_choices("I", 1, "O", True)), [("O", 2, "?", True)])
        self.assertEqual(list(queue_choices("I", 1, "?", True)), [])

    def test_soft_path_can_enter_cavity_but_hard_drop_cannot(self):
        board = board_from_rows(["__________", "XXXX______", "__________", "__________"])
        target = tuple(sorted(((0, 0), (1, 0), (0, 1), (1, 1))))
        hard = reachable_locks(board, "O", self.kicks, "hard")
        soft = reachable_locks(board, "O", self.kicks, "soft")
        self.assertNotIn(target, hard)
        self.assertIn(target, soft)
        self.assertTrue(any(a in ("down", "soft_drop") for a in soft[target]["actions"]))

    def test_canonical_coordinates_survive_prior_line_clears(self):
        board = board_from_rows(["XXXXXXXX__"] * 4)
        ops = canonicalize("O,0,8,0;O,0,8,0", board)
        self.assertEqual(set(ops[0]["original_cells"]), {(8, 0), (9, 0), (8, 1), (9, 1)})
        self.assertEqual(set(ops[1]["original_cells"]), {(8, 2), (9, 2), (8, 3), (9, 3)})

    def test_input_rejects_invalid_symbols_and_full_rows(self):
        self.assertEqual(normalize_queue("jlo stzi | JLO"), "JLOSTZIJLO")
        with self.assertRaises(ValueError):
            normalize_queue("TJ?LO")
        with self.assertRaises(ValueError):
            board_from_rows(["XXXXXXXXXX"])


if __name__ == "__main__":
    unittest.main()
