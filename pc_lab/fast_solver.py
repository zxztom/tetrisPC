"""Bounded first-solution adapter for 2/4/6-row PCs, using sfinder API."""
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

from .engine import board_from_rows, canonicalize, load_kicks, reconstruct,preferred_route
from .solver import ROOT, SFINDER, KICKS, java_path, normalize_queue


def request_kicks(request):
    name=request.get('rotation_rules','SRS')
    if name not in ('SRS','SRS+'):raise ValueError('旋转规则须为 SRS 或 SRS+。')
    return ROOT/'data/srsplus90.properties' if name=='SRS+' else KICKS


def find_pc(queue, rows=None, hold=None, lines=4, mode="hard", allow_hold=True,
            timeout=15, cancelled=lambda: False, progress=lambda *_: None,
            save=True, path_mode=None,kick_path=None,persistent=False):
    queue = "" if isinstance(queue,str) and not queue.strip() and hold else normalize_queue(queue)
    if not isinstance(lines,int) or not 1<=lines<=6:
        raise ValueError("剩余消行数必须为 1 至 6。")
    board = board_from_rows(rows or ["__________"] * lines, max_rows=lines)
    if hold not in (None, "", "I", "J", "L", "O", "S", "T", "Z"):
        raise ValueError("Hold 必须为空或一个方块字母。")
    hold = hold or None
    if mode not in ("hard", "soft"):
        raise ValueError("未知操作规则。")
    occupied = sum(c != "_" for row in board for c in row)
    if (10*lines-occupied) % 4:
        raise ValueError("剩余空格数不能被四格方块整除。")
    required = (10 * lines - occupied) // 4
    if required < 1 or len(queue) + bool(hold) < required:
        raise ValueError(f"需要至少 {required} 个已知可用块。")
    effective = ((hold or "") + queue)[:required + int(allow_hold)]
    folder = None if persistent and not save else ROOT / "output" / ("fast-" + time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    if folder is None:
        field_arg='inline:'+''.join(reversed(board[:lines]))
    else:
        folder.mkdir(parents=True)
        field = folder / "field.txt"
        field.write_text(str(lines) + "\n" + "\n".join(reversed(board[:lines])) + "\n", encoding="utf-8")
        field_arg=str(field)
    bridge = ROOT / "tools/bridge/PcSearch.class"
    if not bridge.is_file():
        raise RuntimeError("缺少快速求解组件，请运行 scripts/build-bridge.ps1。")
    started = time.perf_counter()
    stages = (("soft", "hard") if lines == 6 else ("hard", "soft")) if mode == "soft" else ("hard",)
    if path_mode in ('ground','ground180','groundfine','ground180fine','groundplain','ground180plain'):stages=(path_mode,)
    result = {"status": "no_solution", "queue": queue, "initial_hold": hold,
              "allow_hold": allow_hold, "mode": mode, "target_lines": lines,
              "required_pieces": required, "initial_board": board, "steps": [],
              "candidate_count": 0, "checked_candidates": 0,
              "output_directory": str(folder) if folder else None, "limited_search": False,
              "rules": ("SRS+90" if kick_path and Path(kick_path)!=KICKS else "SRS90")+"，离线几何路径；真实按键由执行器逐步核对。"}
    for search_mode in stages:
        remaining = timeout - (time.perf_counter() - started)
        if remaining <= 0:
            result["status"] = "incomplete"
            break
        progress("searching", f"正在搜索 {lines} 行 PC（{search_mode}）…")
        command = [str(java_path()), "-Xmx384m", "-cp", os.pathsep.join((str(bridge.parent), str(SFINDER))),
                   "PcSearch", field_arg, effective, str(lines), search_mode,
                   "use" if allow_hold else "avoid",str(kick_path or KICKS)]
        if persistent:
            from .search_worker import search
            try:output,returncode=search(command[5:],remaining,cancelled)
            except TimeoutError:
                result['status']='incomplete';break
            if folder is not None:(folder/f'{search_mode}.log').write_text(output,encoding='utf-8')
            if 'SEARCH_BUDGET' in output:
                result['status']='incomplete';break
            if returncode:
                result['status']='incomplete';result['reason']='常驻求解器运行失败。';continue
        else:
            with (folder / f"{search_mode}.log").open("wb") as log:
                process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                try:
                    while process.poll() is None:
                        if cancelled():
                            raise InterruptedError("已停止求解。")
                        if time.perf_counter() - started >= timeout:
                            result["status"] = "incomplete"
                            break
                        time.sleep(.02)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait()
            returncode=process.returncode
            if result["status"] == "incomplete":
                break
            output = (folder / f"{search_mode}.log").read_text(encoding="utf-8", errors="replace")
            if returncode != 0:
                result["status"] = "incomplete"
                result["reason"] = "搜索资源不足或组件运行失败。"
                continue
        result["status"] = "no_solution"
        matches = [line[9:] for line in output.splitlines() if line.startswith("SOLUTION ")]
        if not matches:
            continue
        progress("validating", "正在独立验证 Hold 顺序和可达路径…")
        result["candidate_count"] += 1
        operations = canonicalize(matches[0], board)
        def stop_check():
            if time.perf_counter() - started >= timeout:
                raise TimeoutError("独立路径验证超过时间上限。")
            return cancelled()
        strict=False;steps=None
        if path_mode in ('groundfine','ground180fine'):
            steps=reconstruct(operations,board,queue,hold,allow_hold,
                              load_kicks(kick_path or KICKS),path_mode,stop_check)
            strict=bool(steps)
        if path_mode in ('ground','ground180'):
            # The SAME geometry may have a much better real Hold order.
            # Try that even when Java found it in the normal candidate pass.
            fine_end=min(started+timeout,time.perf_counter()+.015)
            def fine_check():
                if time.perf_counter()>=fine_end:raise TimeoutError('短路线顺序验证预算已用完。')
                return cancelled()
            try:
                steps=reconstruct(operations,board,queue,hold,allow_hold,
                    load_kicks(kick_path or KICKS),path_mode+'fine',fine_check)
            except TimeoutError:pass
            strict=bool(steps)
        if not steps and path_mode not in ('groundfine','ground180fine'):
            steps=reconstruct(operations,board,queue,hold,allow_hold,
                              load_kicks(kick_path or KICKS),path_mode or mode,stop_check)
        result["checked_candidates"] += 1
        if steps:
            for step in steps:step['finesse_standard_finish']=strict
            for step in steps:
                try:
                    if path_mode not in ('ground','ground180','groundfine','ground180fine','groundplain','ground180plain'):step.update(preferred_route(tuple(step['board_before']),step['piece'],step['cells'],load_kicks(kick_path or KICKS)))
                except ValueError:pass  # Offline soft mode can also use a partial soft drop.
            result.update(status="solved", steps=steps,
                          placed_sequence="".join(s["piece"] for s in steps),
                          total_cleared_lines=sum(len(s["cleared_rows"]) for s in steps),
                          final_hold=steps[-1]["hold_after"], queue_index=steps[-1]["queue_index_after"],
                          candidate_search_mode=search_mode)
            result["remaining_known_queue"] = queue[result["queue_index"]:]
            assert result["total_cleared_lines"] == lines and len(steps) == required
            break
        result["status"] = "unverified"
    result["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    result["message"] = (f"{lines} 行 PC 已求解并独立验证。" if result["status"] == "solved"
                         else "搜索未完成，不能判断无解。" if result["status"] == "incomplete"
                         else "布局未通过独立路径验证。" if result["status"] == "unverified"
                         else f"所选规则和已知块序内没有 {lines} 行 PC。")
    if save:
        (folder / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def solve_fast(request, progress=lambda *_: None, cancelled=lambda: False):
    return find_pc(request.get("queue", ""), rows=request.get("rows"), hold=request.get("hold"),
                   lines=request.get("target_lines", 4), mode=request.get("mode", "hard"),
                   allow_hold=request.get("allow_hold", True), timeout=request.get("timeout", 20),
                   progress=progress, cancelled=cancelled,kick_path=request_kicks(request))
