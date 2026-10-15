"""Packed collision checks for grounded SRS routes.

This accelerates the existing route generator, not its reachability rules.
The cell-based engine remains an independent verifier of returned routes.
"""
from functools import lru_cache
from .engine import shape


@lru_cache(maxsize=4096)
def row_mask(row):
    return sum(1<<x for x,c in enumerate(row) if c!='_')


@lru_cache(maxsize=28)
def packed_shape(piece,rotation):
    points=shape(piece,rotation)
    left=min(x for x,y in points);bottom=min(y for x,y in points)
    width=max(x for x,y in points)-left+1;height=max(y for x,y in points)-bottom+1
    mask=sum(1<<((y-bottom)*10+x-left) for x,y in points)
    return left,bottom,10-width,24-height,mask


class GroundGeometry:
    def __init__(self,board,piece,kicks,half_turns):
        self.occupied=sum(row_mask(row)<<(10*y) for y,row in enumerate(board) if row!='__________')
        self.shapes=tuple(packed_shape(piece,r) for r in range(4))
        self.turns={(r,n):kicks[piece+'.'+'NESW'[r]+'NESW'[n]]
                    for r in range(4) for n in ((r+1)%4,(r-1)%4)}
        self.half_turns=half_turns

    def fits(self,x,y,r):
        left,bottom,maxx,maxy,mask=self.shapes[r]
        x+=left;y+=bottom
        return 0<=x<=maxx and 0<=y<=maxy and not self.occupied&(mask<<(10*y+x))

    def settle(self,pose):
        x,y,r=pose
        while self.fits(x,y-1,r):y-=1
        return x,y,r

    def raw_action(self,pose,action):
        x,y,r=pose
        if action in ('left_wall','right_wall'):
            dx=-1 if action=='left_wall' else 1
            # Prefer-soft-drop/20G settles BETWEEN ARR=0 steps.
            while self.fits(x+dx,y,r):x,y,r=self.settle((x+dx,y,r))
            return x,y,r
        if action in ('left','right'):
            x+=-1 if action=='left' else 1
            if self.fits(x,y,r):return x,y,r
        elif action in ('cw','ccw','cw180'):
            nr=(r+(1 if action=='cw' else -1 if action=='ccw' else 2))%4
            offsets=self.half_turns[r] if action=='cw180' else self.turns[r,nr]
            for dx,dy in offsets:
                if self.fits(x+dx,y+dy,nr):return x+dx,y+dy,nr
        raise ValueError('移动或旋转不可达。')
