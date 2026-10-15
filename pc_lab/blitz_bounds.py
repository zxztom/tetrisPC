"""Score envelopes for uninterrupted bag-aligned PC cycles.

This enumerates scoring events and cell conservation, not tetromino
geometry. Maxima are relaxed upper bounds, never claims of playable queues.
"""
from functools import lru_cache
from .blitz import level_lines

@lru_cache(maxsize=None)
def level_at(lines):
    level=1
    while lines>=level_lines(level):lines-=level_lines(level);level+=1
    return level

def score_envelope(pieces,bonuses=True,cycle_lines=(4,4,6)):
    if isinstance(pieces,bool) or not isinstance(pieces,int) or pieces<0:
        raise ValueError('pieces must be a nonnegative integer')
    if not cycle_lines or any(isinstance(n,bool) or not isinstance(n,int) or n<=0 or n%2 for n in cycle_lines):
        raise ValueError('PC heights must be positive even integers')
    cycle_pieces=sum(cycle_lines)*5//2
    if cycle_pieces%7:raise ValueError('cycle must contain whole seven-piece bags')
    boundaries={};count=0;row_cap=0
    for n in cycle_lines:
        count+=n*5//2;row_cap+=n;boundaries[count]=row_cap
    t_stock=cycle_pieces//7
    # (cycle lines, T pieces used for spins, combo, B2B) -> min / max score
    states={(0,0,0,False):(0,0)};completed=0;pcs=0
    actions=[(n,False) for n in range(5 if bonuses else 4)]
    if bonuses:actions += [(n,True) for n in range(4)]
    for number in range(1,pieces+1):
        k=(number-1)%cycle_pieces+1
        cap=next(rows for endpoint,rows in boundaries.items() if k<=endpoint)
        boundary=k in boundaries;new={}
        for (rows,ts,combo,b2b),(low,high) in states.items():
            occupied_before=4*(k-1)-10*rows
            level=level_at(completed*sum(cycle_lines)+rows)
            for lines,spin in actions:
                nr=rows+lines;nt=ts+int(spin)
                if nr>cap or 4*k<10*nr:continue
                if boundary and nr!=cap:continue
                if not boundary and 4*k==10*nr:continue  # no extra two-line PC
                if spin and (nt>min(t_stock,(k+7)//7) or occupied_before==0):continue
                difficult=bool(lines and (spin or lines==4))
                base=(400,800,1200,1600)[lines] if spin else (0,100,300,500,800)[lines]
                if difficult and b2b:base=base*3//2
                gain=(base+(50*combo if lines else 0)+(3500 if boundary else 0))*level
                key=(nr,nt,combo+1 if lines else 0,difficult if lines else b2b)
                lo,hi=new.get(key,(float('inf'),float('-inf')))
                new[key]=(min(lo,low+gain),max(hi,high+gain))
        states=new
        if boundary:pcs+=1
        if k==cycle_pieces:
            completed+=1;reset={}
            for (_,__,combo,b2b),(lo,hi) in states.items():
                key=(0,0,combo,b2b);a,b=reset.get(key,(float('inf'),float('-inf')))
                reset[key]=(min(a,lo),max(b,hi))
            states=reset
    return dict(pieces=pieces,completed_cycles=completed,pcs=pcs,
                min_score=int(min(v[0] for v in states.values())),max_score=int(max(v[1] for v in states.values())),
                completed_cycle_lines=completed*sum(cycle_lines),
                lines_min=completed*sum(cycle_lines)+min(s[0] for s in states),lines_max=completed*sum(cycle_lines)+max(s[0] for s in states),
                geometry_verified=False,drop_points_included=False)

def table(speeds=(4,5,5.55,6,7,8),seconds=120):
    rows=[]
    for pps in speeds:
        pieces=int(pps*seconds);plain=score_envelope(pieces,False);all_scores=score_envelope(pieces,True)
        rows.append(dict(pps=pps,**all_scores,no_spin_no_quad_min=plain['min_score'],
                         no_spin_no_quad_max=plain['max_score']))
    return rows
