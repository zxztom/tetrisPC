"""Research alternate four-piece setup orders on already observed own fields.

Does not reconstruct a seed or read a replay. Only the active/Hold/five Next
actually observed before each setup are supplied to the candidate search.
"""
import argparse,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from pc_lab.setup_order import improve_setup_order
from pc_lab.blitz import Score
from pc_lab.engine import load_kicks,empty_board
from pc_lab.solver import ROOT
from pc_lab.finesse import input_cost


def advance(score,plan):
    for step in plan:score=score.place(len(step['cleared_rows']),step.get('spin','none'),tuple(step['board_after'])==empty_board())
    return score


def minimal(step):
    return {k:step[k] for k in ('piece','hold_used','hold_before','hold_after','queue_index_before',
        'queue_index_after','cells','board_before','board_after','board_placed','cleared_rows','actions','spin')}


def main():
    p=argparse.ArgumentParser();p.add_argument('session',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();sys.stdout.reconfigure(encoding='utf-8')
    d=json.loads(a.session.read_text(encoding='utf-8'));steps=d['steps'];score=Score();checked=0;skipped=0;evidence=[]
    initial=json.loads((a.session.parent/'initial-observation.json').read_text(encoding='utf-8'))
    kicks=load_kicks(ROOT/'data/srsplus90.properties');i=0
    while i<len(steps):
        start=steps[i]
        group=steps[i:i+4]
        if (len(group)==4 and tuple(start['board_before'])==empty_board() and
            all(s.get('strategy')=='pc_setup' for s in group) and start['queue_index_before']==0):
            before=initial if i==0 else dict(active=steps[i-1]['observed_active_after'],next=steps[i-1]['observed_next_after'])
            if not before.get('active') or len(before.get('next',''))<5:
                # Countdown observations can lack an active piece. Do not
                # fill that gap using later historical piece identities.
                skipped+=1;score=advance(score,group);i+=4;continue
            queue=before['active']+before['next'][:5];held=start['hold_before'];checked+=1
            began=time.perf_counter()
            candidate=improve_setup_order(group,queue,held,kicks,score,budget=.012)
            elapsed=time.perf_counter()-began
            if candidate is not group:
                old_score=advance(score,group);new_score=advance(score,candidate)
                assert tuple(candidate[-1]['board_after'])==tuple(group[-1]['board_after'])
                assert candidate[-1]['queue_index_after']==group[-1]['queue_index_after']
                assert candidate[-1]['hold_after']==group[-1]['hold_after']
                evidence.append(dict(first_piece=i+1,visible_queue=queue,hold=held,score_before=score.__dict__,
                    clear_score_gain=new_score.score-old_score.score,planning_seconds=elapsed,
                    original_inputs=sum(input_cost(s['actions'])+s['hold_used'] for s in group),
                    candidate_inputs=sum(input_cost(s['actions'])+s['hold_used'] for s in candidate),
                    original=[minimal(s) for s in group],candidate=[minimal(s) for s in candidate]))
            score=advance(score,group);i+=4
        else:score=advance(score,[start]);i+=1
    result=dict(checked_setups=checked,skipped_missing_start_observation=skipped,changed_setups=len(evidence),
        positive_score_candidates=sum(e['clear_score_gain']>0 for e in evidence),
        reads_seed_or_unseen_queue=False,native_verified=False,
        warning='Historical observed-state geometry comparison; no new random or native score proof.',evidence=evidence)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='evidence'},ensure_ascii=False))


if __name__=='__main__':main()
