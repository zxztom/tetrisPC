"""Unique seven-bag consequences of established source-indexed pieces.

This module has no random generator, replay, game connection or seed.
"""
from .engine import PIECES


def infer_unique_remainders(known):
    result=dict(known);proofs={}
    for start in sorted({i//7*7 for i in known}):
        members=tuple((i,known[i]) for i in range(start,start+7) if i in known)
        pieces=[p for i,p in members]
        if any(p not in PIECES or len(p)!=1 for p in pieces) or len(pieces)!=len(set(pieces)):
            raise ValueError('已知来块不符合七袋规则，不能推导剩余块。')
        if len(members)!=6:continue
        index=next(i for i in range(start,start+7) if i not in known)
        piece=next(p for p in PIECES if p not in pieces)
        result[index]=piece
        proofs[index]=dict(index=index,piece=piece,bag_start=start,established_members=members,
                           reason='six distinct established members of one aligned seven-bag')
    return result,proofs
