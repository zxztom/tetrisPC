"""Blitz rules and bounded planning, with no access to a game seed.

The level parameters come from the official f8f1af8afc4d replay options.
Ground routes settle after every input: holding sonic drop makes these
routes usable at low gravity as well as at 20G. Routes are still verified
against the real sprite before any hard drop.
"""
from heapq import heappush,heappop
from dataclasses import dataclass, asdict
from math import ceil
from functools import lru_cache
import time

from .engine import cells, fits, lock, advance_pose, queue_choices, empty_board

BLITZ_OPTIONS = dict(objective_type='timed', objective_time=120000,
                     levels=True, levelspeed=.42, levelgbase=.65,
                     gravitymay20g=False, nolockout=True, allow180=True,
                     kickset='SRS+', bagtype='7-bag', spinbonuses='T-spins',
                     nextcount=5, locktime=30, lockresets=15,
                     are=0, lineclear_are=0, allclears=True)
JLSTZ_180 = (
    ((0,0),(0,1),(1,1),(-1,1),(1,0),(-1,0)),
    ((0,0),(1,0),(1,2),(1,1),(0,2),(0,1)),
    ((0,0),(0,-1),(-1,-1),(1,-1),(-1,0),(1,0)),
    ((0,0),(-1,0),(-1,2),(-1,1),(0,2),(0,1)),
)
# This independent engine rotates I around a cell rather than SRS's
# half-cell center. Include the anchor offsets, just as srsplus90 does.
I_180 = (((1,-1),(1,0)),((-1,-1),(0,-1)),
         ((-1,1),(-1,0)),((1,1),(0,1)))

def level_lines(level):
    return ceil(5*.42*max(1,int(level)))

def gravity(level):
    level=max(1,int(level));base=.65-.007*(level-1)
    return 1/(60*base**(level-1)) if base>0 else float('inf')

def settle(board,piece,pose):
    x,y,r=pose
    while fits(board,cells(piece,r,x,y-1)):y-=1
    return x,y,r

def raw_ground_action(board,piece,pose,action,kicks):
    x,y,r=pose
    if action in ('left_wall','right_wall'):
        dx=-1 if action=='left_wall' else 1
        # With prefer-soft-drop enabled, TETR.IO settles between ARR=0
        # horizontal steps. Treating it as an airborne teleport crosses
        # cavities the real piece has already fallen into.
        for _ in range(24):
            old=(x,y,r)
            if not fits(board,cells(piece,r,x+dx,y)):return (x,y,r)
            x,y,r=settle(board,piece,(x+dx,y,r))
            if (x,y,r)==old:return (x,y,r)
        return (x,y,r)
    if action=='cw180':
        nr=(r+2)%4
        for dx,dy in (I_180[r] if piece=='I' else JLSTZ_180[r]):
            if fits(board,cells(piece,nr,x+dx,y+dy)):
                return (x+dx,y+dy,nr)
        raise ValueError('180°旋转不可达。')
    return advance_pose(board,piece,pose,action,kicks)

def ground_action(board,piece,pose,action,kicks):
    return settle(board,piece,raw_ground_action(board,piece,pose,action,kicks))

def air_route(board,piece,kicks,start,target,allow180=True,max_inputs=4):
    """Least-finesse-cost direct drop within the physical input limit.

    This only proposes a route. The live executor checks the projected
    cells of the actual moving sprite before committing a hard drop.
    """
    target=tuple(sorted(map(tuple,target)));todo=[(0,0,0,start,())];seen=set();serial=0
    while todo:
        cost,depth,_,pose,path=heappop(todo)
        # A cheaper path can use more physical inputs. Preserve both
        # depths so the cap cannot discard a reachable shorter route.
        key=(pose,depth)
        if key in seen:continue
        seen.add(key);landing=settle(board,piece,pose)
        if tuple(sorted(cells(piece,landing[2],landing[0],landing[1])))==target:
            return dict(x=landing[0],y=landing[1],rotation='0R2L'[landing[2]],actions=list(path)+['hard_drop'],spin='none')
        if len(path)>=max_inputs:continue
        for action in ('left','right','cw','ccw')+(('cw180',) if allow180 and piece!='O' else ())+('left_wall','right_wall'):
            try:
                if action.endswith('_wall'):
                    x,y,r=pose;dx=-1 if action=='left_wall' else 1
                    while fits(board,cells(piece,r,x+dx,y)):x+=dx
                    new=(x,y,r)
                else:new=raw_ground_action(board,piece,pose,action,kicks)
            except ValueError:continue
            if new==pose or (new,depth+1) in seen:continue
            serial+=1
            heappush(todo,(cost+(2 if action=='cw180' else 1),depth+1,serial,new,path+(action,)))
    return None

def ground_locks(board,piece,kicks,start=(4,21,0),allow180=False,wanted=None,max_inputs=12,wanted_spin=None,allow_wall=False,max_cost=None):
    # Choosing and executing a move often ask the same geometric question.
    # Include kick CONTENTS and every reachability constraint; a different
    # config must never inherit a route from a previous rotation system.
    board=tuple(board);start=tuple(start)
    if not fits(board,cells(piece,start[2],start[0],start[1])):return {}
    start=settle(board,piece,start)
    rules=tuple(sorted((key,tuple(map(tuple,offsets))) for key,offsets in kicks.items()))
    frozen=_cached_ground_locks(board,piece,rules,start,allow180,
        tuple(sorted(map(tuple,wanted))) if wanted is not None else None,
        max_inputs,wanted_spin,allow_wall,max_cost)
    # Callers add execution metadata and may replace action lists. Keep
    # cached values immutable, including the actions of each route.
    return {points:dict(x=x,y=y,rotation=rotation,actions=list(actions),spin=spin)
            for points,x,y,rotation,actions,spin in frozen}


@lru_cache(maxsize=512)
def _cached_ground_locks(board,piece,rules,start,allow180,wanted,max_inputs,wanted_spin,allow_wall,max_cost):
    routes=_ground_locks_uncached(board,piece,dict(rules),start,allow180,wanted,max_inputs,wanted_spin,allow_wall,max_cost)
    return tuple((points,route['x'],route['y'],route['rotation'],tuple(route['actions']),route['spin'])
                 for points,route in routes.items())


def ground_cache_info():
    return _cached_ground_locks.cache_info()._asdict()


def clear_ground_cache():
    _cached_ground_locks.cache_clear()


def _ground_locks_uncached(board,piece,kicks,start=(4,21,0),allow180=False,wanted=None,max_inputs=12,wanted_spin=None,allow_wall=False,max_cost=None,fast_geometry=True):
    if not fits(board,cells(piece,start[2],start[0],start[1])):return {}
    if fast_geometry:
        from .ground_geometry import GroundGeometry
        geometry=GroundGeometry(board,piece,kicks,I_180 if piece=='I' else JLSTZ_180)
        settle_pose=geometry.settle;raw_action=geometry.raw_action
    else:
        # Retain the cell-based route generator for independent comparisons.
        settle_pose=lambda pose:settle(board,piece,pose)
        raw_action=lambda pose,action:raw_ground_action(board,piece,pose,action,kicks)
    start=settle_pose(start)
    todo=[(0,0,start,(),'none')];serial=0
    seen=set();result={}
    while todo:
        cost,_,pose,path,spin=heappop(todo)
        if (pose,spin) in seen:continue
        seen.add((pose,spin))
        points=tuple(sorted(cells(piece,pose[2],pose[0],pose[1])))
        candidate=dict(x=pose[0],y=pose[1],rotation='0R2L'[pose[2]],
                       actions=list(path)+['hard_drop'],spin=spin)
        old=result.get(points)
        old_cost=sum(2 if a=='cw180' else 1 for a in old['actions'][:-1]) if old else 99
        spin_rank={'none':0,'mini':1,'full':2}
        if old is None or (cost,-spin_rank[spin])<(old_cost,-spin_rank[old['spin']]):
            result[points]=candidate
        if wanted==points and (wanted_spin is None or spin==wanted_spin):return {points:candidate}
        if len(path)>=max_inputs or max_cost is not None and cost>=max_cost:continue
        for action in ('left','right','cw','ccw')+(('cw180',) if allow180 and piece!='O' else ())+(('left_wall','right_wall') if allow_wall else ()):
            try:
                raw=raw_action(pose,action)
                new=settle_pose(raw)
            except ValueError:continue
            if new==pose:continue
            rotated=action in ('cw','ccw','cw180')
            upgrade=False
            if rotated and action!='cw180':
                x,y,r=pose;nr=(r+(1 if action=='cw' else -1))%4
                offsets=kicks[piece+'.'+'NESW'[r]+'NESW'[nr]]
                for index,(dx,dy) in enumerate(offsets):
                    if fits(board,cells(piece,nr,x+dx,y+dy)):
                        upgrade=index==4;break
            # TETR.IO sets spin flags at rotation time. A rotation followed
            # by falling into three corners isn't a spin (native replay
            # regression: CUSTOM piece 276). Drop preserves existing flags.
            next_spin=t_spin(board,piece,raw,action,upgrade) if rotated and raw==new else 'none'
            key=(new,next_spin)
            if key in seen:continue
            serial+=1
            heappush(todo,(cost+(2 if action=='cw180' else 1),serial,new,path+(action,),next_spin))
    return {} if wanted is not None else result

def t_spin(board,piece,pose,last_action,kick_upgrade=False):
    if piece!='T' or last_action not in ('cw','ccw','cw180'):return 'none'
    x,y,r=pose
    def filled(dx,dy):
        nx,ny=x+dx,y+dy
        return not (0<=nx<10 and 0<=ny<len(board)) or board[ny][nx]!='_'
    corners=[filled(-1,1),filled(1,1),filled(1,-1),filled(-1,-1)]
    if sum(corners)<3:return 'none'
    facing=((0,1),(1,2),(2,3),(3,0))[r]
    return 'full' if all(corners[i] for i in facing) or kick_upgrade else 'mini'

@dataclass(frozen=True)
class Score:
    level:int=1
    level_progress:int=0
    lines:int=0
    score:int=0
    combo:int=0
    b2b:int=0
    pcs:int=0
    tspins:int=0
    level_cap:int|None=None

    def place(self,lines,spin='none',pc=False,drop_cells=0):
        difficult=lines>0 and (lines==4 or spin!='none')
        b2b=(self.b2b+1 if difficult else 0) if lines else self.b2b
        combo=self.combo+1 if lines else 0
        base=((400,800,1200,1600)[lines] if spin=='full' else
              (100,200,400,800)[lines] if spin=='mini' else (0,100,300,500,800)[lines])
        if difficult and self.b2b:base=base*3//2
        gain=(base+50*max(0,combo-1)+(3500 if pc else 0))*self.level
        # Drop points use the level too; kept separate from clear/B2B bonus.
        gain+=round(drop_cells*self.level)
        level=self.level;progress=self.level_progress+lines
        while (self.level_cap is None or level<self.level_cap) and progress>=level_lines(level):
            progress-=level_lines(level);level+=1
        return Score(level,progress,self.lines+lines,self.score+gain,combo,b2b,
                     self.pcs+int(pc),self.tspins+int(spin!='none'),self.level_cap)

    def to_dict(self):return asdict(self)

@lru_cache(maxsize=4096)
def _occupied_columns(row):
    return tuple(x for x,c in enumerate(row) if c!='_')


def board_cost(board,multi_well=False):
    # Count occupied cells and their vertical moments in one sparse pass.
    # The triangular sum is exactly the old sum of depths of empty cells,
    # including enclosed cavities; no heuristic weights have changed.
    heights=[0]*10;counts=[0]*10;moments=[0]*10
    for y,row in enumerate(board):
        if row=='__________':continue
        for x in _occupied_columns(row):
            heights[x]=y+1;counts[x]+=1;moments[x]+=y+1
    holes=sum(heights)-sum(counts)
    covered=sum(h*(h+1)//2-(h+1)*n+m for h,n,m in zip(heights,counts,moments))
    bumps=sum(abs(a-b) for a,b in zip(heights,heights[1:]))
    # A right well is cheap only when reachable; holes dominate everything.
    mass=sum(heights);maxh=max(heights)
    cost=140*holes+10*covered+5*bumps+2.5*mass+6*maxh+18*max(0,maxh-8)**2
    if multi_well:
        # Preserve one deep well for quads. Several deep narrow wells
        # compete for scarce vertical filling pieces and accumulate stack.
        depths=sorted(max(0,min(heights[x-1] if x else 24,
                               heights[x+1] if x<9 else 24)-h) for x,h in enumerate(heights))
        cost+=18*sum(d*(d+1)//2 for d in depths[:-1] if d>=3)
    return cost

def score_move(board,active,next_queue,held,kicks,score,start=(4,21,0),
               hold_available=True,allow180=False,budget=.065,cancelled=lambda:False,allow_wall=False,finesse_only=False,multi_well=False,fault_penalty=10):
    """Anytime two-ply search: PC/T-spins/quad rewards, survival first.

    Every candidate is grounded-reachable. Only current, Hold and visible
    Next are used, including the extra queue consumption of an empty Hold.
    A complete first-ply pass precedes optional lookahead, so timeout cannot
    accidentally return a placement for a different active piece.
    """
    from .finesse import estimated_faults
    deadline=time.perf_counter()+budget;queue=active+next_queue;candidates=[]
    for piece,index,after_hold,use_hold in queue_choices(queue,0,held,hold_available):
        route_start=(4,21,0) if use_hold else start
        for points,route in ground_locks(board,piece,kicks,route_start,allow180,allow_wall=allow_wall).items():
            if finesse_only and estimated_faults(piece,points,route['actions']):continue
            after,placed,cleared=lock(board,points,piece)
            pc=after==empty_board();s=score.place(len(cleared),route['spin'],pc)
            reward=(s.score-score.score)/max(1,score.level)/9
            value=reward-board_cost(after,multi_well)-.6*len(route['actions'])-2*use_hold-fault_penalty*estimated_faults(piece,points,route['actions'])
            step=dict(piece=piece,hold_used=use_hold,hold_before=held,hold_after=after_hold,
                      queue_index_before=0,queue_index_after=index,cells=points,
                      board_before=board,board_placed=placed,board_after=after,
                      cleared_rows=cleared,strategy='score_survival',**route)
            candidates.append([value,step,s])
    if not candidates:raise ValueError('当前地面位置没有可执行落点。')
    candidates.sort(key=lambda c:c[0],reverse=True)
    best=candidates[0];best_value=float('-inf')
    for value,step,s in candidates[:8]:
        if cancelled():raise InterruptedError('已停止 Blitz 规划。')
        if time.perf_counter()>=deadline:break
        after=tuple(step['board_after']);index=step['queue_index_after'];future=[]
        for piece,_,_,_ in queue_choices(queue,index,step['hold_after'],True):
            for points,route in ground_locks(after,piece,kicks,allow180=allow180,allow_wall=allow_wall).items():
                if finesse_only and estimated_faults(piece,points,route['actions']):continue
                b,_,lines=lock(after,points,piece);ss=s.place(len(lines),route['spin'],b==empty_board())
                future.append((ss.score-s.score)/max(1,s.level)/9-board_cost(b,multi_well)-.6*len(route['actions'])-fault_penalty*estimated_faults(piece,points,route['actions']))
            if time.perf_counter()>=deadline:break
        if future:
            combined=value*.35+max(future)*.65
            if combined>best_value:best_value=combined;best=[value,step,s]
    return best[1]
