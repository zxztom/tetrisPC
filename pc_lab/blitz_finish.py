"""Budgeted visible-queue PC score/finesse refinement.

An independently verified incumbent survives every budget expiry. No
unobserved future piece is played or used by this enumeration.
"""
import time
from .engine import queue_choices,lock,empty_board
from .blitz import ground_locks
from .finesse import estimated_faults,input_cost

def promote_spin(board,piece,target,kicks,route,allow180=True,allow_wall=True,extra_inputs=0):
    if piece!='T' or route.get('spin')=='full':return route
    extra_inputs=max(0,min(1,int(extra_inputs)))
    for spin in ('full','mini'):
        choices=ground_locks(board,piece,kicks,allow180=allow180,allow_wall=allow_wall,
                             wanted=tuple(sorted(map(tuple,target))),wanted_spin=spin,max_inputs=5+extra_inputs)
        better=next(iter(choices.values()),None)
        if not better:continue
        added=input_cost(better['actions'])-input_cost(route['actions'])
        # A local scoring candidate retains the exact occupied cells. Allow
        # one extra quick input, never an extra DAS charge, when explicitly
        # testing score rather than minimum reference input count.
        walls=lambda r:sum(a.endswith('_wall') for a in r['actions'])
        if added<=extra_inputs and (added<=0 or walls(better)<=walls(route)):
            return dict(better,spin_extra_input_cost=added) if added>0 else better
    return route

def improve_finish(board,queue,held,kicks,score,lines,incumbent,allow180=True,
                   allow_wall=True,budget=.025,hold_available=True,save_dpc_extra=False,cancelled=lambda:False,
                   score_first=False,max_faults=None):
    required=(lines*10-sum(c!='_' for row in board for c in row))//4
    if not 1<=required<=4 or len(queue)+bool(held)<required:return incumbent
    deadline=time.perf_counter()+max(0,budget);best=incumbent;cache={};visits={}
    def rank(plan):
        s=score;faults=0;inputs=0
        for step in plan:
            s=s.place(len(step['cleared_rows']),step.get('spin','none'),tuple(step['board_after'])==empty_board())
            faults+=estimated_faults(step['piece'],step['cells'],step['actions'])
            inputs+=input_cost(step['actions'])+int(step['hold_used'])
        extra=plan[-1]['hold_after'] if plan else held
        save=({'O':3,'S':3,'Z':3,'I':2,'J':1,'L':1,'T':0}.get(extra,0) if save_dpc_extra else 0)
        return (s.score,-faults,save,-inputs) if score_first else (-faults,save,s.score,-inputs)
    best_rank=rank(incumbent)
    def visit(b,index,hold,remaining,history,s,faults):
        nonlocal best,best_rank
        if time.perf_counter()>=deadline:return
        if cancelled():raise InterruptedError('已停止 PC 得分优化。')
        if max_faults is not None and faults>max_faults:return
        if not remaining:
            if b==empty_board():
                r=rank(history)
                if r>best_rank:best=history;best_rank=r
            return
        if not score_first and faults>-best_rank[0]:return
        key=(b,index,hold,remaining,s.combo,s.b2b,faults if max_faults is not None else None)
        value=(-s.score,faults) if score_first else (faults,-s.score)
        if key in visits and visits[key]<=value:return
        visits[key]=value
        candidates=[]
        for piece,after_index,after_hold,use_hold in queue_choices(queue,index,hold,True):
            if not history and use_hold and not hold_available:continue
            if (b,piece) not in cache:
                cache[b,piece]=ground_locks(b,piece,kicks,allow180=allow180,allow_wall=allow_wall)
            for points,route in cache[b,piece].items():
                cap=lines-sum(len(a['cleared_rows']) for a in history)
                if max(y for x,y in points)>=cap:continue
                after,placed,cleared=lock(b,points,piece)
                f=estimated_faults(piece,points,route['actions'])
                ns=s.place(len(cleared),route.get('spin','none'),after==empty_board())
                step=dict(piece=piece,hold_used=use_hold,hold_before=hold,hold_after=after_hold,
                          queue_index_before=index,queue_index_after=after_index,cells=points,
                          board_before=b,board_placed=placed,board_after=after,cleared_rows=cleared,
                          strategy='pc_score_finish',**route)
                candidates.append((f,-ns.score,input_cost(route['actions']),step,ns))
        candidates.sort(key=(lambda a:(a[1],a[0],a[2])) if score_first else (lambda a:a[:3]))
        for f,_,__,step,ns in candidates:
            if time.perf_counter()>=deadline:break
            visit(step['board_after'],step['queue_index_after'],step['hold_after'],remaining-1,history+[step],ns,faults+f)
    visit(board,0,held,required,[],score,0)
    return best
