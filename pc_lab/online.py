"""Limited-preview planning. Forecasts are hypotheses, never observations."""
from collections import Counter
import random
import time

from .engine import PIECES
from .fast_solver import find_pc


def resolve_observed_hold(step,state):
    """Bind a symbolic carry piece only after that active piece is observed.

    A finite-preview solution may finish by playing the known Hold while
    storing an active piece beyond the entered preview. '?' is a carry
    placeholder, never a tetromino to place or a pixel value to wait for.
    """
    piece=step.get('piece')
    if not isinstance(piece,str) or len(piece)!=1 or piece not in PIECES:raise ValueError('不能放置未知方块。')
    result=dict(step)
    for name,value in (('hold_before',state['hold']),('hold_after',state['active'] if step['hold_used'] else state['hold'])):
        if result.get(name)=='?':
            if not isinstance(value,str) or len(value)!=1 or value not in PIECES:raise ValueError('未知 Hold 尚未得到实际画面确认。')
            result[name]=value
    return result


def observation_consistent(known,revealed):
    if any(i in known and known[i]!=p for i,p in revealed.items()):return False
    merged={**known,**revealed}
    for start in {i//7*7 for i in revealed}:
        pieces=[merged[i] for i in range(start,start+7) if i in merged]
        if len(pieces)!=len(set(pieces)):return False
    return True


def complete_bags(known, end, randomizer):
    result=[]
    for bag_start in range(0,end,7):
        seen=[known[i] for i in range(bag_start,bag_start+7) if i in known]
        if len(seen)!=len(set(seen)):
            raise ValueError("识别到的来块不符合七袋规则，请重新开始并校准。")
        missing=[p for p in PIECES if p not in seen]
        randomizer.shuffle(missing)
        for i in range(bag_start,min(bag_start+7,end)):
            result.append(known[i] if i in known else missing.pop())
    return "".join(result)


def all_placements_observed(steps,known,current,held_source,cycle_end,hold_available=True):
    """An unknown carried piece is allowed; an unknown locked piece isn't."""
    if not steps:return False
    for number,step in enumerate(steps):
        if not number and step['hold_used'] and not hold_available:return False
        active=current+step['queue_index_before']
        source=(held_source if held_source is not None else active+1) if step['hold_used'] else active
        if source not in known or source>=cycle_end or known[source]!=step['piece']:return False
        if step['hold_used']:held_source=active
    return True


def choose_plan(known, current, held_source, board, remaining_lines, cycle_end,
                samples=8, cancelled=lambda:False,hold_available=True,kick_path=None,time_budget=None,persistent=False,path_mode='instant',coverage=False,
                observed_finish_first=False,visible_finish_stats=None,deduce_bag=False):
    established_count=len(known);deductions=[]
    occupied=sum(c!="_" for row in board for c in row)
    required=(remaining_lines*10-occupied)//4
    end=min(cycle_end,current+required+(held_source is None))
    if deduce_bag:
        from .bag_knowledge import infer_unique_remainders
        known,proofs=infer_unique_remainders(known)
        deductions=[proof for i,proof in proofs.items() if current<=i<end or i==held_source]
    unknown=any(i not in known for i in range(current,end))
    forecasts=max(1,samples if unknown else 1)
    # An inferred singleton does not change the random hypotheses of bags
    # that remain ambiguous. It only changes what is provably determined.
    rng=random.Random(current*104729+established_count*997)
    votes={};tried=set();started=time.perf_counter();scenarios=[]
    probe_status=None
    if observed_finish_first and unknown:
        visible_end=current
        while visible_end<end and visible_end in known:visible_end+=1
        held=known[held_source] if held_source is not None else None
        if visible_end-current+int(held is not None)>=required:
            if cancelled():raise InterruptedError('已停止可见来块收尾。')
            budget=min(.035,time_budget*.35) if time_budget is not None else .035
            if budget>=.004:
                if visible_finish_stats is not None:visible_finish_stats['probes']+=1
                try:
                    plan=find_pc(''.join(known[i] for i in range(current,visible_end)),
                        rows=list(reversed(board[:remaining_lines])),hold=held,lines=remaining_lines,mode='soft',
                        path_mode=path_mode,timeout=budget,cancelled=cancelled,kick_path=kick_path,persistent=persistent,save=False)
                    probe_status=plan['status']
                    if plan['status']=='solved' and all_placements_observed(plan['steps'],known,current,held_source,cycle_end,hold_available):
                        if visible_finish_stats is not None:visible_finish_stats['plans']+=1
                        return [dict(s,future_was_unknown=False,observed_finish=True,
                                     seven_bag_deductions=deductions,
                                     unknown_carry=any(a.get('hold_after')=='?' for a in plan['steps']),
                                     forecast_samples=0,forecast_support=0,planning_seconds=round(time.perf_counter()-started,3)) for s in plan['steps']]
                except TimeoutError:probe_status='incomplete'
                if probe_status=='incomplete' and visible_finish_stats is not None:visible_finish_stats['incomplete']+=1
    seed_budget=time_budget*.55 if coverage and unknown and time_budget is not None else time_budget
    for _ in range(forecasts):
        if cancelled():raise InterruptedError("已停止实时规划。")
        remaining_budget=None if seed_budget is None else seed_budget-(time.perf_counter()-started)
        if remaining_budget is not None and remaining_budget<.01:break
        forecast=complete_bags(known,end,rng)
        prefix=forecast[current:end]
        if prefix in tried:continue
        tried.add(prefix)
        scenarios.append((prefix,None))
        held=known[held_source] if held_source is not None else None
        rows=list(reversed(board[:remaining_lines]))
        timeout=3 if unknown else 15
        if remaining_budget is not None:timeout=min(timeout,remaining_budget)
        try:
            plan=find_pc(prefix,rows=rows,hold=held,lines=remaining_lines,mode="soft",
                         path_mode=path_mode,timeout=timeout,cancelled=cancelled,kick_path=kick_path,persistent=persistent,save=False)
        except TimeoutError:continue
        if plan["status"]!="solved":continue
        step=plan["steps"][0]
        if step["hold_used"] and not hold_available:continue
        source=(held_source if held_source is not None else current+1) if step["hold_used"] else current
        if source not in known or source>=cycle_end:
            continue
        key=(step["piece"],step["hold_used"],tuple(sorted(map(tuple,step["cells"]))))
        if key not in votes:votes[key]={"count":0,"step":step,"steps":plan["steps"]}
        votes[key]["count"]+=1
        scenarios[-1]=(prefix,key)
        if not unknown:break
    if not votes:
        raise PlanningFailure("可见 Next 下尚未找到可执行的继续方案；未来预测不等于实际来块。")
    best=max(votes.values(),key=lambda vote:(vote["count"],-len(vote["step"]["actions"])))
    metadata=dict(forecast_samples=len(tried),forecast_support=best["count"],
                  future_was_unknown=unknown,planning_seconds=round(time.perf_counter()-started,3))
    if deductions:metadata['seven_bag_deductions']=deductions
    if probe_status is not None:metadata['observed_probe_status']=probe_status
    if coverage and unknown and len(votes)>1 and scenarios:
        from .forecast_coverage import compare_first_moves
        report=compare_first_moves(votes,scenarios,remaining_lines,
            started+(time_budget if time_budget is not None else .1),cancelled,kick_path,persistent,path_mode)
        metadata['coverage_compared']=bool(report)
        if report:
            metadata.update(coverage_changed=report['vote'] is not best,
                            coverage_successes=report['successes'],coverage_samples=report['samples'],
                            coverage_candidates=report['candidates'],coverage_candidate_successes=report['candidate_successes'])
            best=report['vote']
            metadata['forecast_support']=best['count']
        metadata['planning_seconds']=round(time.perf_counter()-started,3)
    # A verified finish made of established pieces (visible, or uniquely
    # derived from an aligned seven-bag) stays valid after its first move.
    # Keep it rather than replacing it with a different solver candidate.
    return [dict(step,**metadata) for step in (best["steps"] if not unknown else [best["step"]])]


class PlanningFailure(RuntimeError):
    pass


def choose_move(*args,**kwargs):
    return choose_plan(*args,**kwargs)[0]
