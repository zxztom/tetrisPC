"""Bounded solution-finder adapter with independently verified replay."""
from pathlib import Path
import json
import os
import re
import subprocess
import time
import uuid

from .engine import (PIECES, board_from_rows, canonicalize, load_kicks,
                     reconstruct)

ROOT = Path(__file__).resolve().parent.parent
SFINDER = ROOT / "tools" / "solution-finder" / "sfinder.jar"
KICKS = ROOT / "tools" / "solution-finder" / "kicks" / "srs.properties"


def java_path():
    options = sorted((ROOT / "tools" / "java").glob("*/bin/java.exe"))
    if not options:
        raise RuntimeError("缺少便携 Java，请先运行 scripts/setup.ps1。")
    if not SFINDER.is_file():
        raise RuntimeError("缺少 PC 求解器，请先运行 scripts/setup.ps1。")
    return options[0]


def normalize_queue(value):
    if not isinstance(value, str):
        raise ValueError("请输入块序。")
    queue = re.sub(r"[\s,|/]+", "", value.upper())
    if not queue or len(queue) > 80 or any(c not in PIECES for c in queue):
        raise ValueError("块序只能包含 I J L O S T Z，可用空格或 | 分隔，最多 80 块。")
    return queue


def solve(request, progress=lambda *_: None, cancelled=lambda: False):
    started = time.monotonic()
    queue = normalize_queue(request.get("queue", ""))
    initial = board_from_rows(request.get("rows", ["__________"] * 4))
    if request.get("target_lines", 4) != 4:
        raise ValueError("第一版只求解四行 PC。")
    allow_hold = request.get("allow_hold", True)
    if not isinstance(allow_hold, bool):
        raise ValueError("Hold 开关必须为布尔值。")
    held = request.get("hold") or None
    if held is not None:
        if not isinstance(held, str) or held.upper() not in PIECES or len(held) != 1:
            raise ValueError("Hold 必须为空或一个方块字母。")
        held = held.upper()
    if held and not allow_hold:
        raise ValueError("关闭 Hold 时请清空初始 Hold。")
    mode = request.get("mode", "hard")
    if mode not in ("hard", "soft"):
        raise ValueError("未知的操作规则。")
    occupied = sum(c != "_" for row in initial for c in row)
    if occupied % 4:
        raise ValueError("初始堆积格数必须为 4 的倍数，才能达成四行 PC。")
    required = (40 - occupied) // 4
    if len(queue) + bool(held) < required:
        raise ValueError(f"还需放置 {required} 块；请提供足够的已知块序或初始 Hold。")
    # A single hold can only access one extra input beyond the placed count.
    effective = ((held or "") + queue)[:required + int(allow_hold)]
    # Enumerating every unrestricted ten-piece layout can exhaust the Java
    # heap. For large searches use the hard-drop subset, but validate its
    # layout order with the requested movement rules. Failure is INCOMPLETE,
    # never proof that the wider soft-drop search has no solution.
    search_mode = "hard" if mode == "soft" and required > 6 else mode
    limited_search = search_mode != mode
    job_dir = ROOT / "output" / (time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    job_dir.mkdir(parents=True)
    normalized = {"queue": queue, "hold": held, "rows": list(reversed(initial[:4])),
                  "allow_hold": allow_hold, "mode": mode, "target_lines": 4}
    (job_dir / "request.json").write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    field_path = job_dir / "field.txt"
    field_path.write_text("4\n" + "\n".join(reversed(initial[:4])) + "\n", encoding="utf-8")
    command = [str(java_path()), "-Xmx512m", "-jar", str(SFINDER), "path",
               "-fp", str(field_path), "-p", effective,
               "-H", "use" if allow_hold else "avoid", "-c", "4", "-K", "srs",
               "-d", search_mode, "-f", "csv", "-k", "none",
               "-L", "1", "-th", "2", "-o", str(job_dir / "path.csv"),
               "-lp", str(job_dir / "solver.log")]
    progress("searching", "正在优先搜索硬降布局，再验证允许软降的操作路径…" if limited_search
             else "正在搜索四行 PC 候选布局…")
    log_path = job_dir / "console.log"
    with log_path.open("wb") as log:
        process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        try:
            while process.poll() is None:
                if cancelled():
                    raise InterruptedError("已停止求解。")
                if time.monotonic() - started > 60:
                    raise TimeoutError("搜索超过 60 秒，已停止；这不代表无解。可减少已知块或填入开局地形。")
                time.sleep(0.05)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
    raw_path = job_dir / "path_unique.csv"
    if process.returncode != 0 or not raw_path.is_file():
        if "OutOfMemoryError" in log_path.read_text(encoding="utf-8", errors="replace"):
            raise RuntimeError("搜索达到内存上限，已停止；这不代表无解。请使用硬降模式或填入开局地形。详情见 " + str(log_path))
        raise RuntimeError("求解器运行失败，详情见 " + str(log_path))
    with raw_path.open(encoding="utf-8") as handle:
        candidate_count = sum(bool(line.strip()) for line in handle)
    result = {"status": "no_solution", "queue": queue, "initial_hold": held,
              "allow_hold": allow_hold, "mode": mode, "target_lines": 4,
              "required_pieces": required, "initial_board": initial,
              "candidate_search_mode": search_mode, "limited_search": limited_search,
              "candidate_count": candidate_count, "checked_candidates": 0,
              "steps": [], "output_directory": str(job_dir),
              "rules": "离线 SRS90；不模拟重力、锁定延迟或 TETR.IO SRS+/180°。"}
    if candidate_count:
        progress("validating", f"找到 {candidate_count} 个候选，正在验证块序与合法路径…")
        kicks = load_kicks(KICKS)
        with raw_path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                if cancelled():
                    raise InterruptedError("已停止求解。")
                if result["checked_candidates"] >= 3000 or time.monotonic() - started > 90:
                    result["status"] = "incomplete"
                    break
                result["checked_candidates"] += 1
                operations = canonicalize(line, initial)
                def should_stop():
                    if time.monotonic() - started > 90:
                        raise TimeoutError("路径验证超过 90 秒，已停止；这不代表无解。")
                    return cancelled()
                steps = reconstruct(operations, initial, queue, held, allow_hold,
                                    kicks, mode, should_stop)
                if steps:
                    result["status"] = "solved"
                    result["steps"] = steps
                    result["placed_sequence"] = "".join(step["piece"] for step in steps)
                    result["total_cleared_lines"] = sum(len(step["cleared_rows"]) for step in steps)
                    result["final_hold"] = steps[-1]["hold_after"]
                    result["queue_index"] = steps[-1]["queue_index_after"]
                    result["remaining_known_queue"] = queue[result["queue_index"]:]
                    result["active_piece_known"] = result["queue_index"] < len(queue)
                    assert len(steps) == required and result["total_cleared_lines"] == 4
                    break
        if not result["steps"] and result["status"] != "incomplete":
            result["status"] = "unverified"
    if limited_search and not result["steps"]:
        result["status"] = "incomplete"
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    messages = {
        "solved": "已找到并验证四行 PC，可逐块回放。",
        "no_solution": "在所选规则和已知块序内未找到四行 PC。",
        "unverified": "候选布局未通过真实块序与操作路径验证，不能作为可执行方案。",
        "incomplete": "搜索未完成，尚未找到可执行方案；不能据此判断无解。",
    }
    result["message"] = messages[result["status"]]
    if limited_search:
        result["message"] += (" 本次优先搜索硬降布局。" if result["steps"] else
                              " 本次仅搜索了硬降布局；完整软降搜索限于剩余不超过 6 块的地形。")
    (job_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
