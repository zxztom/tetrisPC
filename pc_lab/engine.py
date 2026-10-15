"""Independent board simulation and SRS90 path validation.

Coordinates match solution-finder: x=0 is left, y=0 is bottom. This
offline model loads either SRS or SRS+ 90-degree kicks. Gravity, timing
and 180-degree rotations are outside this geometric model.
"""
from collections import deque
from functools import lru_cache
from pathlib import Path
import re

WIDTH, HEIGHT = 10, 24
PIECES = "IJLOSTZ"
BASE = {
    "T": ((0, 0), (-1, 0), (1, 0), (0, 1)),
    "I": ((0, 0), (-1, 0), (1, 0), (2, 0)),
    "L": ((0, 0), (-1, 0), (1, 0), (1, 1)),
    "J": ((0, 0), (-1, 0), (1, 0), (-1, 1)),
    "S": ((0, 0), (-1, 0), (0, 1), (1, 1)),
    "Z": ((0, 0), (1, 0), (0, 1), (-1, 1)),
    "O": ((0, 0), (1, 0), (0, 1), (1, 1)),
}
ROTATIONS = "0R2L"


@lru_cache(maxsize=None)
def shape(piece, rotation):
    points = BASE[piece]
    for _ in range(rotation):
        points = tuple((y, -x) for x, y in points)
    return points


def cells(piece, rotation, x, y):
    return tuple((x + dx, y + dy) for dx, dy in shape(piece, rotation))


def empty_board():
    return tuple("_" * WIDTH for _ in range(HEIGHT))


def board_from_rows(rows, max_rows=6):
    """Input rows are top to bottom; internal rows are bottom to top."""
    if not isinstance(rows, list) or len(rows) > max_rows:
        raise ValueError(f"初始棋盘最多 {max_rows} 行。")
    if any(not isinstance(row, str) or len(row) != 10 or
           any(c not in "_X" + PIECES for c in row) for row in rows):
        raise ValueError("棋盘每行必须为十格，使用 _、X 或方块字母。")
    board = tuple(reversed(rows)) + empty_board()[len(rows):]
    if any("_" not in row for row in board):
        raise ValueError("初始棋盘不能包含已经填满的行，请先消行。")
    return board


def fits(board, points):
    return all(0 <= x < WIDTH and 0 <= y < HEIGHT and board[y][x] == "_"
               for x, y in points)


def lock(board, points, piece):
    if len(set(points)) != 4 or not fits(board, points):
        raise ValueError("方块落点重叠或超出棋盘。")
    # Only the four occupied rows can change. Search evaluates thousands
    # of locks; copying and joining all 24 rows dominated that work.
    rows = list(board)
    changed = {}
    for x, y in points:
        if y not in changed:changed[y] = list(rows[y])
        changed[y][x] = piece
    for y, row in changed.items():rows[y] = "".join(row)
    placed = tuple(rows)
    cleared = tuple(y for y, row in enumerate(placed) if "_" not in row)
    remaining = tuple(row for y, row in enumerate(placed) if y not in cleared)
    after = remaining + empty_board()[:len(cleared)]
    return after, placed, cleared


def load_kicks(path):
    raw = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, value = line.split("=", 1)
            raw[key.strip()] = value.strip()
    def resolve(key):
        value = raw[key]
        if value.startswith("&"):
            return resolve(value[1:])
        return tuple((int(x), int(y)) for x, y in
                     re.findall(r"\(\s*@?\s*([+-]?\d+)\s*,\s*([+-]?\d+)\s*\)", value))
    return {key: resolve(key) for key in raw}


def reachable_locks(board, piece, kicks, mode="hard", start=(4,21,0), wanted=None):
    """BFS returns each reachable four-cell lock and its abstract actions.

    Hard mode allows movement/rotation at spawn height, then hard drop.
    Soft mode also allows one-cell down moves and SRS90 kicks. No 180.
    """
    if mode in ('groundplain','ground180plain'):mode=mode.removesuffix('plain')
    if mode in ('ground180','groundfine','ground180fine'):
        from .blitz import ground_locks
        from .finesse import estimated_faults,lower_bounds
        routes=ground_locks(board,piece,kicks,start,allow180='180' in mode,wanted=wanted,
                            allow_wall=mode.endswith('fine'),max_cost=max(lower_bounds(piece).values()) if mode.endswith('fine') else None)
        if mode.endswith('fine'):
            routes={points:route for points,route in routes.items() if estimated_faults(piece,points,route['actions'])==0}
        return routes
    if not fits(board, cells(piece, start[2], start[0], start[1])):
        return {}
    if mode == 'ground':
        x,y,r=start
        while fits(board,cells(piece,r,x,y-1)):y-=1
        start=x,y,r
    parents = {start: None}
    todo = deque([start])
    landings = {}
    directions = "NESW"
    def path_to(state):
        result = []
        while parents[state] is not None:
            previous, action = parents[state]
            result.append(action)
            state = previous
        return list(reversed(result))
    while todo:
        state = todo.popleft()
        x, y, rotation = state
        drop_y = y
        while fits(board, cells(piece, rotation, x, drop_y - 1)):
            drop_y -= 1
        target = tuple(sorted(cells(piece, rotation, x, drop_y)))
        if target not in landings:
            landings[target] = {"x": x, "y": drop_y, "rotation": ROTATIONS[rotation],
                                "actions": path_to(state) + ["hard_drop"]}
            if wanted is not None and target==wanted:return landings
        successors = [(x - 1, y, rotation, "left"), (x + 1, y, rotation, "right")]
        if mode == "soft":
            successors.append((x, y - 1, rotation, "down"))
        if mode in ("soft", "instant"):
            successors.append((x, drop_y, rotation, "soft_drop"))
        moves=successors;successors=[]
        for turn, action in ((1, "cw"), (-1, "ccw")):
            next_r = (rotation + turn) % 4
            key = piece + "." + directions[rotation] + directions[next_r]
            for dx, dy in kicks[key]:
                if fits(board, cells(piece, next_r, x + dx, y + dy)):
                    successors.append((x + dx, y + dy, next_r, action))
                    break  # Only the FIRST valid SRS kick is legal.
        successors.extend(moves)
        for nx, ny, nr, action in successors:
            if mode == 'ground':
                while fits(board,cells(piece,nr,nx,ny-1)):ny-=1
            next_state = (nx, ny, nr)
            if next_state not in parents and fits(board, cells(piece, nr, nx, ny)):
                parents[next_state] = (state, action)
                todo.append(next_state)
    return landings


def preferred_route(board,piece,points,kicks,start=(4,21,0)):
    """Prefer a rotation at spawn and direct drop to this exact lock.

    A surface tuck is used only when no air-only path reaches the target.
    """
    target=tuple(sorted(map(tuple,points)))
    route=reachable_locks(board,piece,kicks,'hard',start,wanted=target).get(target)
    if route is None:route=reachable_locks(board,piece,kicks,'instant',start,wanted=target).get(target)
    if route is None:raise ValueError('当前旋转规则下无法到达计划落点。')
    return route


def poses_for(piece, points):
    """Recover all equivalent SRS poses from the four observed cells."""
    target=set(map(tuple,points));result=[]
    if len(target)!=4:return result
    for rotation in range(4):
        offsets=shape(piece,rotation)
        x=min(p[0] for p in target)-min(p[0] for p in offsets)
        y=min(p[1] for p in target)-min(p[1] for p in offsets)
        if set(cells(piece,rotation,x,y))==target:result.append((x,y,rotation))
    return result


def dropped_cells(board,piece,pose):
    x,y,r=pose
    while fits(board,cells(piece,r,x,y-1)):y-=1
    return cells(piece,r,x,y)


def falls_to(board,piece,previous,actual):
    """A pose may descend naturally but never pass through occupied cells."""
    previous=set(map(tuple,previous));actual=set(map(tuple,actual))
    if len(previous)!=4 or len(actual)!=4:return False
    dy=min(y for x,y in actual)-min(y for x,y in previous)
    return dy<=0 and {(x,y+dy) for x,y in previous}==actual and all(
        fits(board,[(x,y+d) for x,y in previous]) for d in range(dy,1))


def advance_pose(board,piece,pose,action,kicks):
    x,y,r=pose
    if action in ('left','right'):x+=-1 if action=='left' else 1
    elif action=='soft_drop':
        while fits(board,cells(piece,r,x,y-1)):y-=1
    elif action in ('cw','ccw'):
        nr=(r+(1 if action=='cw' else -1))%4
        for dx,dy in kicks[piece+'.'+'NESW'[r]+'NESW'[nr]]:
            if fits(board,cells(piece,nr,x+dx,y+dy)):x,y,r=x+dx,y+dy,nr;break
        else:raise ValueError('旋转不可达。')
    else:raise ValueError('未知动作。')
    if not fits(board,cells(piece,r,x,y)):raise ValueError('移动不可达。')
    return x,y,r


def canonicalize(csv_line, initial_board):
    """Undo line deletions in an sfinder sample to get original-row cells.

    CSV order is a valid example, but can differ from the supplied queue.
    Original-row labels let us safely reconstruct another placement order.
    """
    board = initial_board
    labels = list(range(HEIGHT))
    operations = []
    for entry in csv_line.strip().split(";"):
        piece, rot, sx, sy = entry.split(",")
        points = cells(piece, ROTATIONS.index(rot), int(sx), int(sy))
        board, _, cleared = lock(board, points, piece)
        operations.append({"piece": piece,
                           "original_cells": tuple(sorted((x, labels[y]) for x, y in points))})
        labels = [label for y, label in enumerate(labels) if y not in cleared]
        labels.extend(range(max(labels, default=-1) + 1, max(labels, default=-1) + 1 + len(cleared)))
    if any(c != "_" for row in board for c in row):
        raise ValueError("求解器输出未清空棋盘。")
    return operations


def queue_choices(queue, index, held, allow_hold):
    """Index points at the active piece; each branch includes one lock.

    '?' is an unknown active/held piece beyond the entered preview. A
    known held piece may still be played by swapping with that unknown.
    No branch ever places an unknown piece.
    """
    active = queue[index] if index < len(queue) else "?"
    if active != "?":
        yield active, index + 1, held, False
    if not allow_hold:
        return
    if held and held != "?":
        yield held, index + 1, active, True
    elif held is None and index + 1 < len(queue):
        yield queue[index + 1], index + 2, active, True


def reconstruct(operations, initial_board, queue, held, allow_hold, kicks,
                mode, cancelled=lambda: False, final_board=None,initial_hold_available=True):
    failed = set()
    reach_cache = {}
    def visit(board, labels, remaining, index, hold):
        if cancelled():
            raise InterruptedError("已停止求解。")
        if not remaining:
            return [] if (board==final_board if final_board is not None else
                          all(row == "_" * 10 for row in board)) else None
        key = (board, labels, remaining, index, hold)
        if key in failed:
            return None
        for piece, next_index, next_hold, use_hold in queue_choices(queue, index, hold, allow_hold):
            if use_hold and len(remaining)==len(operations) and not initial_hold_available:continue
            cache_key = (board, piece)
            if cache_key not in reach_cache:
                reach_cache[cache_key] = reachable_locks(board, piece, kicks, mode)
            reachable = reach_cache[cache_key]
            label_to_y = {label: y for y, label in enumerate(labels)}
            seen = set()
            for op_id in remaining:
                op = operations[op_id]
                if op["piece"] != piece or op["original_cells"] in seen:
                    continue
                seen.add(op["original_cells"])
                if any(y not in label_to_y for _, y in op["original_cells"]):
                    continue
                points = tuple(sorted((x, label_to_y[y]) for x, y in op["original_cells"]))
                route = reachable.get(points)
                if route is None:
                    continue
                after, placed, cleared = lock(board, points, piece)
                next_labels = tuple(label for y, label in enumerate(labels) if y not in cleared)
                next_labels += tuple(range(max(labels) + 1, max(labels) + 1 + len(cleared)))
                rest = visit(after, next_labels, tuple(i for i in remaining if i != op_id),
                             next_index, next_hold)
                if rest is not None:
                    return [{"piece": piece, "hold_used": use_hold, "hold_before": hold,
                             "hold_after": next_hold, "queue_index_before": index,
                             "queue_index_after": next_index, "cells": points,
                             **route, "board_before": board, "board_placed": placed,
                             "board_after": after, "cleared_rows": cleared}] + rest
        failed.add(key)
        return None
    return visit(initial_board, tuple(range(HEIGHT)), tuple(range(len(operations))), 0, held)
