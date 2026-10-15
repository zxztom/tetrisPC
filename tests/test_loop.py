import json
import random
import unittest
from pathlib import Path

from pc_lab.loop import plan_loop
from pc_lab.rng import seeded_queue
from pc_lab.fast_solver import find_pc
from pc_lab.online import complete_bags


class LoopTests(unittest.TestCase):
    def test_seed_matches_observed_tetrio_preview(self):
        # Captured from TETR.IO's custom mode, seed=1234, random seed=OFF.
        self.assertEqual(seeded_queue(1234,7),"ITJSOLZ")

    def test_five_bags_produce_exactly_three_pcs(self):
        result=plan_loop({"queue":"JSTZOLISIOLZTJTOSZJILTJSOLIZJSILTZO","mode":"soft"})
        self.assertEqual(result["status"],"solved")
        self.assertEqual(len(result["steps"]),35)
        self.assertEqual(result["total_cleared_lines"],14)
        self.assertEqual(sorted(s["source_index"] for s in result["steps"]),list(range(35)))
        empty=[i+1 for i,s in enumerate(result["steps"]) if all(r=="__________" for r in s["board_after"])]
        self.assertEqual(empty,[10,20,35])

    def test_real_time_path_contains_no_single_cell_soft_drop(self):
        result=find_pc(seeded_queue(1234,35),lines=4,mode="soft",path_mode="instant")
        self.assertEqual(result["status"],"solved")
        self.assertTrue(all("down" not in s["actions"] for s in result["steps"]))

    def test_forecasts_preserve_observations_and_seven_bag(self):
        known={0:"I",1:"T",2:"J",3:"S",4:"O",5:"L",6:"Z",7:"O",8:"S"}
        queue=complete_bags(known,21,random.Random(42))
        for i,p in known.items():self.assertEqual(queue[i],p)
        for start in (0,7,14):self.assertEqual(set(queue[start:start+7]),set("IJLOSTZ"))

    def test_forecasts_reject_conflicting_bag(self):
        with self.assertRaises(ValueError):
            complete_bags({0:"I",1:"I"},7,random.Random(1))


if __name__=="__main__":unittest.main()
