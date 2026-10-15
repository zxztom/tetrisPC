"""Offline same-cell T-spin candidates from already observed own session fields.

No replay, seed or unseen queue is read. This is geometry evidence only;
native score and execution time must still be measured in new games.
"""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from pc_lab.blitz import ground_locks
from pc_lab.blitz_finish import promote_spin
from pc_lab.engine import load_kicks
from pc_lab.finesse import input_cost
from pc_lab.solver import ROOT


def main():
    p=argparse.ArgumentParser();p.add_argument('session',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();sys.stdout.reconfigure(encoding='utf-8')
    d=json.loads(a.session.read_text(encoding='utf-8'));kicks=load_kicks(ROOT/'data/srsplus90.properties')
    evidence=[];checked=0
    for i,step in enumerate(d['steps']):
        if step['piece']!='T':continue
        board=tuple(step['board_before']);target=tuple(sorted(map(tuple,step['cells'])))
        route=ground_locks(board,'T',kicks,allow180=True,allow_wall=True,wanted=target).get(target)
        if route is None:continue
        checked+=1
        old=promote_spin(board,'T',target,kicks,route,extra_inputs=0)
        new=promote_spin(board,'T',target,kicks,route,extra_inputs=1)
        if old.get('spin')!=new.get('spin'):
            evidence.append(dict(piece_number=i+1,board=board,target=target,old=old,new=new,
                extra_reference_cost=input_cost(new['actions'])-input_cost(old['actions']),
                originally_air=bool(step.get('lock_proof',{}).get('air'))))
    result=dict(session=str(a.session.resolve()),checked_t_fields=checked,candidates=len(evidence),
        reads_seed_or_future_queue=False,native_verified=False,
        warning='Same-cell candidates only. Additional soft-drop, processing and input time are not simulated.',
        evidence=evidence)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='evidence'},ensure_ascii=False))


if __name__=='__main__':main()
