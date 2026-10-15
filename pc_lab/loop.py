"""35-piece cycle planning, preserving source identities across Hold."""
from collections import Counter
import json
import time
import uuid

from .engine import PIECES
from .fast_solver import find_pc,request_kicks
from .solver import ROOT, normalize_queue
from .dpc import seeded_dpc
from .cycles import cycle_spec


def validate_bags(queue):
    for start in range(0, len(queue) - 6, 7):
        if Counter(queue[start:start + 7]) != Counter(PIECES):
            raise ValueError(f"第 {start // 7 + 1} 包不是完整的七袋块序。")


def plan_loop(request, progress=lambda *_: None, cancelled=lambda: False):
    stage_lines,cycle_size=cycle_spec(request.get('cycle_mode','dpc'))
    queue = normalize_queue(request.get("queue", ""))
    if len(queue) < cycle_size:
        raise ValueError(f"完整离线循环需要至少 {cycle_size//7} 包（{cycle_size} 块）已知块序。实时模式从窗口逐段读取。")
    validate_bags(queue)
    queue = queue[:cycle_size]
    index, held, held_source = 0, None, None
    stages, steps = [], []
    started = time.monotonic()
    mode = request.get("mode", "soft")
    kick_path=request_kicks(request)
    for number, lines in enumerate(stage_lines, 1):
        if cancelled():
            raise InterruptedError("已停止循环求解。")
        progress("searching", f"循环第 {number} 段：{lines} 行 PC…")
        # At DPC we expose only the remaining pieces of the first five bags.
        # A final Hold may swap with an unknown future piece but cannot place it.
        stage = (seeded_dpc(queue,index,held_source,0,35,cancelled) if lines==6 and mode=="soft" and request.get('rotation_rules','SRS')=='SRS' else
                 find_pc(queue[index:], hold=held, lines=lines, mode=mode, timeout=25,
                         cancelled=cancelled, progress=progress,kick_path=kick_path))
        if stage["status"] != "solved":
            return {"status": stage["status"], "message": f"第 {number} 段尚未完成：" + stage["message"],
                    "queue": queue, "stages": stages, "steps": steps,
                    "elapsed_seconds": round(time.monotonic()-started, 3)}
        base = index
        for local in stage["steps"]:
            before = base + local["queue_index_before"]
            active_source = before
            if local["hold_used"]:
                if held_source is None:
                    held_source = before
                    active_source = before + 1
                else:
                    active_source, held_source = held_source, before
            copied = dict(local)
            copied.update(stage=number, stage_lines=lines, source_index=active_source,
                          global_queue_index_before=before,
                          global_queue_index_after=base + local["queue_index_after"])
            if active_source >= cycle_size or queue[active_source] != local["piece"]:
                raise RuntimeError("循环使用了边界外的方块。")
            steps.append(copied)
        index = base + stage["queue_index"]
        held = stage["final_hold"]
        stages.append({"number": number, "lines": lines, "pieces": len(stage["steps"]),
                       "queue_index": index, "hold": held,
                       "elapsed_seconds": stage["elapsed_seconds"]})
    identities = [step["source_index"] for step in steps]
    if sorted(identities) != list(range(cycle_size)):
        raise RuntimeError("循环的七袋方块没有各使用一次。")
    pc_indices=[i+1 for i,step in enumerate(steps) if all(row=="__________" for row in step["board_after"])]
    expected=[];count=0
    for lines in stage_lines:count+=lines*10//4;expected.append(count)
    if pc_indices!=expected:raise RuntimeError("方案没有保持所选循环的全清检查点。")
    result = {"status": "solved", "message": f"{cycle_size} 块、{len(stage_lines)} 次 PC 的循环已逐块验证。",
              "cycle_mode":request.get('cycle_mode','dpc'),
              "queue": queue, "target_lines": sum(stage_lines), "initial_board": steps[0]["board_before"],
              "initial_hold": None, "steps": steps, "stages": stages, "mode": mode,
              "placed_sequence": "".join(step["piece"] for step in steps),
              "total_cleared_lines": sum(stage_lines), "final_hold": held, "queue_index": index,
              "bag_cycle_verified": True, "candidate_count": len(stage_lines), "checked_candidates": len(stage_lines),
              "elapsed_seconds": round(time.monotonic() - started, 3)}
    folder = ROOT / "output" / ("loop-" + time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    folder.mkdir()
    result["output_directory"] = str(folder)
    (folder / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
