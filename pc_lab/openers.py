"""Standard PCO first-bag structures from the user's Hard Drop reference."""
from .engine import empty_board,load_kicks,reconstruct
from .solver import KICKS
from .solver import ROOT
import json
from functools import lru_cache

PCO_ROWS=("LLL_____SS","LOO____SST","JOO___ZZTT","JJJ____ZZT")


def pco_setup(known,current,held_source,cycle_start,cancelled=lambda:False,hold_available=True,kicks=None,path_mode='instant'):
    bag_end=cycle_start+7
    if any(i not in known for i in range(cycle_start,bag_end)):
        return None
    queue="".join(known[i] for i in range(current,bag_end))
    hold=known[held_source] if held_source is not None else None
    kicks=kicks or load_kicks(KICKS)
    for use_i in (False,True):
        for flip_left,flip_right in ((False,False),(True,False),(False,True),(True,True)):
            rows=[list(row) for row in reversed(PCO_ROWS)]
            if flip_left:
                for row in rows:
                    row[:3]=[{"J":"L","L":"J"}.get(c,c) for c in reversed(row[:3])]
            if flip_right:
                for row in rows:
                    row[6:]=[{"S":"Z","Z":"S"}.get(c,c) for c in reversed(row[6:])]
            if use_i:
                for row in rows:row[3]="I"
            goal=tuple("".join(row) for row in rows)+empty_board()[4:]
            pieces=sorted(set(c for row in rows for c in row if c!="_"))
            operations=[{"piece":piece,"original_cells":tuple((x,y) for y,row in enumerate(rows)
                                                                  for x,c in enumerate(row) if c==piece)}
                        for piece in pieces]
            steps=reconstruct(operations,empty_board(),queue,hold,True,kicks,path_mode,cancelled,goal,
                              initial_hold_available=hold_available)
            if steps:
                return steps
    return None


@lru_cache(maxsize=1)
def dpc_patterns():
    return json.loads((ROOT/"data/dpc-setups.json").read_text(encoding="utf-8"))["setups"]


def dpc_setups(known,current,held_source,cycle_start,cancelled=lambda:False,kicks=None,path_mode='instant',prefer_scoring=False):
    bag_start=cycle_start+21;bag_end=cycle_start+28
    # Six visible members of a bag determine the seventh exactly.
    present=[known[i] for i in range(bag_start,bag_end) if i in known]
    missing_indices=[i for i in range(bag_start,bag_end) if i not in known]
    if len(missing_indices)==1 and len(set(present))==6:
        known[missing_indices[0]]=next(iter(set("IJLOSTZ")-set(present)))
    if any(i not in known for i in range(current,bag_end)):return
    extra=known[held_source] if held_source is not None else known.get(current)
    queue="".join(known[i] for i in range(current,bag_end))
    hold=known[held_source] if held_source is not None else None
    swap={"J":"L","L":"J","S":"Z","Z":"S"}
    patterns=dpc_patterns()
    if prefer_scoring:
        preferred=('L/J -> O (TSD DPC)','S/Z -> O (Lime DPC)','JL -> O (Pelican DPC)')
        patterns=sorted(patterns,key=lambda t:preferred.index(t['name']) if t['name'] in preferred else len(preferred))
    for template in patterns:
        for mirrored in (False,True):
            extra_type=swap.get(template["extra"],template["extra"]) if mirrored else template["extra"]
            if extra_type!=extra:continue
            rows=[list(row) for row in reversed(template["rows"])]
            if mirrored:
                rows=[[("'" if label.startswith("'") else "")+swap.get(label.lstrip("'"),label.lstrip("'"))
                       if label!='_' else '_' for label in reversed(row)] for row in rows]
            labels=sorted({label for row in rows for label in row if label!='_'})
            operations=[{"piece":label.lstrip("'"),"original_cells":tuple((x,y) for y,row in enumerate(rows)
                                                                    for x,c in enumerate(row) if c==label)}
                        for label in labels]
            physical=tuple("".join(label.lstrip("'") for label in row) for row in rows)
            # Full setup rows will clear as its seven pieces are assembled.
            physical=tuple(row for row in physical if '_' in row)
            goal=physical+empty_board()[len(physical):]
            steps=reconstruct(operations,empty_board(),queue,hold,True,kicks or load_kicks(KICKS),path_mode,cancelled,goal)
            if steps:
                for step in steps:step["opener"]=template["name"]
                yield steps


def dpc_setup(known,current,held_source,cycle_start,cancelled=lambda:False,kicks=None):
    return next(dpc_setups(known,current,held_source,cycle_start,cancelled,kicks),None)
