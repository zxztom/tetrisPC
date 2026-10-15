"""Empty-field input lower bounds, independent of the real game seed.

These are planning estimates, not substitutes for native finesse stats.
Physical footprints merge I/S/Z's equivalent rotation states.
"""
from functools import lru_cache
from heapq import heappush, heappop
from .engine import empty_board, cells, fits, load_kicks
from .solver import ROOT

def footprint(points):
    floor=min(y for x,y in points)
    return tuple(sorted((x,y-floor) for x,y in points))

def input_cost(actions):
    return sum(2 if a=='cw180' else 1 for a in actions if a not in ('hard_drop','soft_drop','hold'))

@lru_cache(maxsize=7)
def lower_bounds(piece):
    from .blitz import raw_ground_action
    board=empty_board();kicks=load_kicks(ROOT/'data/srsplus90.properties')
    todo=[(0,(4,21,0))];seen={};result={}
    while todo:
        cost,pose=heappop(todo)
        if pose in seen:continue
        seen[pose]=cost;key=footprint(cells(piece,pose[2],pose[0],pose[1]))
        result[key]=min(cost,result.get(key,99))
        # A standard two-quarter-turn reference also permits a 180 input.
        # Native high-gravity checkpoint deltas agree with weight two.
        for action in ('left','right','cw','ccw','left_wall','right_wall'):
            if piece=='O' and action in ('cw','ccw','cw180'):continue
            try:
                if action.endswith('_wall'):
                    x,y,r=pose;dx=-1 if action=='left_wall' else 1
                    while fits(board,cells(piece,r,x+dx,y)):x+=dx
                    new=(x,y,r)
                else:new=raw_ground_action(board,piece,pose,action,kicks)
            except ValueError:continue
            if new not in seen:heappush(todo,(cost+(2 if action=='cw180' else 1),new))
    return result

def estimated_faults(piece,points,actions):
    return max(0,input_cost(actions)-lower_bounds(piece).get(footprint(points),0))
