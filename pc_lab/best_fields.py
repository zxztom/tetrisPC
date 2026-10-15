"""Phase-aware public four-piece setups, verified against actual preview.

The source's percentages rank fields; every offered setup is independently
checked for the selected kick table and observed queue order.
"""
from collections import Counter
from functools import lru_cache
import json

from .engine import empty_board,reconstruct
from .solver import ROOT


@lru_cache(maxsize=1)
def fields():
    file=ROOT/'data/best-chance-fields.json'
    return json.loads(file.read_text(encoding='utf-8'))['fields'] if file.is_file() else []


def field_setups(known,current,held_source,phase,kicks,cancelled=lambda:False,hold_available=True,limit=4,path_mode='instant',prefer_finesse=False,finesse_weight=.5):
    hold=known[held_source] if held_source is not None else None
    size=4 if hold else 5
    if any(i not in known for i in range(current,current+size)):return []
    queue=''.join(known[i] for i in range(current,current+size))
    available=Counter((hold or '')+queue)
    swap={'J':'L','L':'J','S':'Z','Z':'S'}
    candidates=[f for f in fields() if f['phase']==phase and
                (not(Counter(f['signature'])-available) or
                 not(Counter(swap.get(p,p) for p in f['signature'])-available))]
    candidates.sort(key=lambda f:-f['reported_coverage'])
    setups=[];seen=set()
    def select():
        if not prefer_finesse:return setups
        from .blitz import ground_locks
        from .finesse import estimated_faults,input_cost
        ranked=[]
        for plan in setups:
            faults=inputs=0
            for step in plan:
                target=tuple(sorted(map(tuple,step['cells'])))
                route=ground_locks(tuple(step['board_before']),step['piece'],kicks,
                                  allow180='180' in path_mode,allow_wall=True,wanted=target).get(target)
                if route:step.update(route)
                faults+=estimated_faults(step['piece'],step['cells'],step['actions'])
                inputs+=input_cost(step['actions'])+int(step['hold_used'])
            ranked.append((-(plan[0]['source_reported_coverage']-finesse_weight*faults),inputs,plan))
        return [a[2] for a in sorted(ranked,key=lambda a:a[:2])]
    for field in candidates:
        try:
            if cancelled():raise InterruptedError('已停止地形选择。')
        except TimeoutError:
            if setups:return select()
            raise
        for mirror in (False,True):
            signature=Counter(swap.get(p,p) if mirror else p for p in field['signature'])
            if signature-available:continue
            rows=field['rows']
            if mirror:rows=[''.join(swap.get(p,p) for p in reversed(row)) for row in rows]
            physical=tuple(row for row in reversed(rows) if '_' in row)
            goal=physical+empty_board()[len(physical):]
            if goal in seen:continue
            seen.add(goal)
            for variant in field['operations']:
                ops=[{'piece':swap.get(op['piece'],op['piece']) if mirror else op['piece'],
                      'original_cells':tuple(sorted((9-x if mirror else x,y) for x,y in op['original_cells']))}
                     for op in variant]
                try:
                    route=reconstruct(ops,empty_board(),queue,hold,True,kicks,path_mode,cancelled,goal,
                                      initial_hold_available=hold_available)
                except TimeoutError:
                    if setups:return select()
                    raise
                if route:
                    for step in route:step.update(opener='Best Chance Field',setup_phase=phase,
                                                source_setup_cleared_lines=4-len(physical),
                                                source_reported_coverage=field['reported_coverage'],source_url=field['source_image'])
                    setups.append(route);break
            if len(setups)>=limit:return select()
    return select()
