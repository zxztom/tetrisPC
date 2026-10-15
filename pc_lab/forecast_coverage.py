"""Cross-check candidate first moves on the same hypothetical bag tails.

This is a sampled lower bound, not an exact PC probability. Incomplete
searches are unknown. Only a completed, equally tested comparison can
replace the independently verified incumbent first move.
"""
import time
from .fast_solver import find_pc
from .engine import empty_board


def move_key(step):
    return step['piece'],step['hold_used'],tuple(sorted(map(tuple,step['cells'])))


def compare_first_moves(votes,forecasts,remaining_lines,deadline,
                        cancelled=lambda:False,kick_path=None,persistent=False,path_mode='instant'):
    records=[]
    for key,vote in votes.items():
        step=vote['step'];cases=[]
        if step.get('hold_after')=='?':return None
        for queue,seed_key in forecasts:
            if cancelled():raise InterruptedError('已停止候选覆盖比较。')
            if key==seed_key:
                cases.append('solved');continue
            budget=deadline-time.perf_counter()
            if budget<.004:return None
            lines=remaining_lines-len(step['cleared_rows'])
            if lines==0:
                cases.append('solved' if tuple(step['board_after'])==empty_board() else 'no_solution');continue
            try:
                result=find_pc(queue[step['queue_index_after']:],
                    rows=list(reversed(step['board_after'][:lines])),hold=step['hold_after'],lines=lines,
                    mode='soft',allow_hold=True,timeout=min(.018,budget),cancelled=cancelled,
                    save=False,kick_path=kick_path,persistent=persistent,path_mode=path_mode)
            except (TimeoutError,ValueError):return None
            if result['status'] not in ('solved','no_solution'):return None
            cases.append(result['status'])
        records.append(dict(key=key,vote=vote,successes=cases.count('solved'),cases=cases))
    if not records:return None
    from .finesse import input_cost
    best=max(records,key=lambda r:(r['successes'],-input_cost(r['vote']['step']['actions'])))
    return dict(vote=best['vote'],successes=best['successes'],samples=len(forecasts),
                candidates=len(records),candidate_successes=[r['successes'] for r in records])
