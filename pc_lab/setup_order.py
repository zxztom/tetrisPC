"""Optional bounded scoring of a known setup's placement order.

Keeps the identical final board, queue position and held piece. Every cell
and every placed piece is from the incumbent and the visible queue. This
research helper is not enabled in the live planner by default.
"""
import time
from .engine import empty_board,queue_choices,lock
from .blitz import ground_locks
from .blitz_finish import promote_spin
from .finesse import input_cost


def improve_setup_order(incumbent,queue,held,kicks,score,*,budget=.008,
                        allow180=True,allow_wall=True,hold_available=True,
                        cancelled=lambda:False):
    if budget<=0 or not 1<=len(incumbent)<=4 or tuple(incumbent[0]['board_before'])!=empty_board():return incumbent
    if incumbent[0]['queue_index_before']!=0:return incumbent
    deadline=time.perf_counter()+max(0,budget)
    goal=tuple(incumbent[-1]['board_after']);end_index=incumbent[-1]['queue_index_after']
    end_hold=incumbent[-1]['hold_after'];labels=tuple(range(len(empty_board())));ops=[]
    for step in incumbent:
        ops.append((step['piece'],tuple((x,labels[y]) for x,y in step['cells'])))
        labels=tuple(label for y,label in enumerate(labels) if y not in step['cleared_rows'])+tuple(
            range(max(labels)+1,max(labels)+1+len(step['cleared_rows'])))
    cache={}
    def route_for(b,piece,points):
        key=(b,piece,points)
        if key not in cache:
            r=ground_locks(b,piece,kicks,allow180=allow180,allow_wall=allow_wall,wanted=points).get(points)
            cache[key]=promote_spin(b,piece,points,kicks,r,allow180,allow_wall) if r else None
        return cache[key]
    def costs(plan):
        return (sum(input_cost(s['actions'])+int(s['hold_used']) for s in plan),
                sum(a.endswith('_wall') for s in plan for a in s['actions']))
    baseline=[]
    for step in incumbent:
        b=tuple(step['board_before']);points=tuple(sorted(map(tuple,step['cells'])))
        r=route_for(b,step['piece'],points)
        if r is None:return incumbent
        baseline.append(dict(step,**r))
    input_cap,wall_cap=costs(baseline)
    def rank(plan):
        s=score
        for step in plan:s=s.place(len(step['cleared_rows']),step.get('spin','none'),tuple(step['board_after'])==empty_board())
        inputs,walls=costs(plan)
        return s.score,int(s.b2b),s.combo,-inputs,-walls
    best=incumbent;best_rank=rank(baseline)
    metadata={k:v for k,v in incumbent[0].items() if k in (
        'opener','setup_phase','source_setup_cleared_lines','source_reported_coverage','source_url','strategy')}
    def visit(b,labels,remaining,index,hold,history,inputs,walls):
        nonlocal best,best_rank
        if cancelled():raise InterruptedError('已停止搭建顺序研究。')
        if time.perf_counter()>=deadline:return
        if inputs>input_cap+1 or walls>wall_cap:return
        if not remaining:
            if b==goal and index==end_index and hold==end_hold:
                value=rank(history)
                if value>best_rank:best=history;best_rank=value
            return
        y_map={label:y for y,label in enumerate(labels)}
        for piece,next_index,next_hold,use_hold in queue_choices(queue,index,hold,True):
            if next_index>end_index or not history and use_hold and not hold_available:continue
            for op_id in remaining:
                p,original=ops[op_id]
                if p!=piece or any(y not in y_map for x,y in original):continue
                if time.perf_counter()>=deadline:return
                points=tuple(sorted((x,y_map[y]) for x,y in original))
                r=route_for(b,piece,points)
                if r is None:continue
                after,placed,cleared=lock(b,points,piece)
                next_labels=tuple(label for y,label in enumerate(labels) if y not in cleared)+tuple(
                    range(max(labels)+1,max(labels)+1+len(cleared)))
                step=dict(piece=piece,hold_used=use_hold,hold_before=hold,hold_after=next_hold,
                    queue_index_before=index,queue_index_after=next_index,cells=points,
                    board_before=b,board_placed=placed,board_after=after,cleared_rows=cleared,**r,**metadata)
                visit(after,next_labels,tuple(i for i in remaining if i!=op_id),next_index,next_hold,
                    history+[step],inputs+input_cost(r['actions'])+int(use_hold),
                    walls+sum(a.endswith('_wall') for a in r['actions']))
    visit(empty_board(),tuple(range(len(empty_board()))),tuple(range(len(ops))),0,held,[],0,0)
    return best
