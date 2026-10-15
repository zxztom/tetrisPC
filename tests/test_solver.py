"""Integration checks against the real solver plus independent path replay."""
import unittest

from pc_lab.engine import cells, fits, load_kicks, lock, ROTATIONS
from pc_lab.solver import KICKS, solve


class SolverTests(unittest.TestCase):
    def verify(self, result):
        self.assertEqual(result["status"], "solved", result["message"])
        board = tuple(result["initial_board"])
        queue, index, hold = result["queue"], 0, result["initial_hold"]
        total = 0
        kicks = load_kicks(KICKS)
        for step in result["steps"]:
            active = queue[index] if index < len(queue) else "?"
            if step["hold_used"]:
                if hold:
                    active, hold = hold, active
                else:
                    hold = active
                    index += 1
                    active = queue[index]
            self.assertEqual(active, step["piece"])
            index += 1
            self.assertEqual(hold, step["hold_after"])
            self.assertEqual(index, step["queue_index_after"])
            x, y, rotation = 4, 21, 0
            self.assertTrue(fits(board, cells(active, rotation, x, y)))
            for action in step["actions"]:
                if action in ("left", "right"):
                    x += -1 if action == "left" else 1
                elif action == "down":
                    y -= 1
                elif action in ("cw", "ccw"):
                    next_r = (rotation + (1 if action == "cw" else -1)) % 4
                    key = active + "." + "NESW"[rotation] + "NESW"[next_r]
                    for dx, dy in kicks[key]:
                        if fits(board, cells(active, next_r, x + dx, y + dy)):
                            x, y, rotation = x + dx, y + dy, next_r
                            break
                    else:
                        self.fail("A recorded rotation cannot execute")
                elif action in ("hard_drop", "soft_drop"):
                    while fits(board, cells(active, rotation, x, y - 1)):
                        y -= 1
                else:
                    self.fail("Unknown action")
                self.assertTrue(fits(board, cells(active, rotation, x, y)))
            points = cells(active, rotation, x, y)
            self.assertEqual(set(points), set(map(tuple, step["cells"])))
            self.assertFalse(fits(board, cells(active, rotation, x, y - 1)))
            board, _, cleared = lock(board, points, active)
            self.assertEqual(board, tuple(step["board_after"]))
            total += len(cleared)
        self.assertEqual(total, 4)
        self.assertTrue(all(row == "__________" for row in board))

    def test_empty_board_real_seven_bag_prefix(self):
        self.verify(solve({"queue": "JLOSTZI | JLO", "mode": "hard"}))

    def test_endgame_with_initial_hold(self):
        result = solve({"rows": ["XXXXXXXX__"] * 4, "queue": "TOI", "hold": "O"})
        self.verify(result)
        self.assertEqual(result["placed_sequence"], "OO")
        self.assertEqual(result["final_hold"], "T")
        self.assertEqual(result["remaining_known_queue"], "I")

    def test_hard_endgame_without_hold(self):
        self.verify(solve({"rows": ["XXXXXXXX__"] * 4, "queue": "OO", "allow_hold": False}))

    def test_no_solution_is_distinct_from_execution_error(self):
        result = solve({"rows": ["XXXXXXXX__"] * 4, "queue": "TT", "allow_hold": False})
        self.assertEqual(result["status"], "no_solution")
        self.assertEqual(result["candidate_count"], 0)
        self.assertEqual(result["steps"], [])

    def test_soft_empty_board_uses_bounded_search(self):
        result = solve({"queue": "JLOSTZIJLO", "mode": "soft"})
        self.verify(result)
        self.assertTrue(result["limited_search"])
        self.assertEqual(result["candidate_search_mode"], "hard")

    def test_soft_endgame_uses_full_soft_search(self):
        result = solve({"rows": ["XXXXXXXX__"] * 4, "queue": "OO", "mode": "soft"})
        self.verify(result)
        self.assertFalse(result["limited_search"])
        self.assertEqual(result["candidate_search_mode"], "soft")

    def test_limited_soft_failure_is_not_reported_as_no_solution(self):
        result = solve({"queue": "SSSSSSSSSS", "mode": "soft", "allow_hold": False})
        self.assertEqual(result["status"], "incomplete")

    def test_cancellation(self):
        with self.assertRaises(InterruptedError):
            solve({"queue": "JLOSTZIJLO"}, cancelled=lambda: True)


if __name__ == "__main__":
    unittest.main()
