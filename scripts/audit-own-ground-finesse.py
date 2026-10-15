"""Historic route comparison; no replay options, seeds, or future pieces."""
import json,sys,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from pc_lab.blitz import ground_locks,Score,gravity
from pc_lab.engine import load_kicks,empty_board
from pc_lab.finesse import estimated_faults
from pc_lab.solver import ROOT

p=argparse.ArgumentParser()
p.add_argument('--session',type=Path,required=True);p.add_argument('--replay',type=Path,required=True)
p.add_argument('--output',type=Path,required=True);args=p.parse_args()
session=json.loads(args.session.read_text(encoding='utf-8'))
replay=json.loads(args.replay.read_text(encoding='utf-8'))
checkpoints=[dict(frame=e['frame'],stats=e['data']['stats']) for e in replay['replay']['events'] if e['type']=='full']
native=replay['replay'].get('results',{}).get('stats') or checkpoints[-1]['stats']
profile=session.get('simulation_profile','blitz')
kicks=load_kicks(ROOT/'data/srsplus90.properties');score=Score(level=15 if profile=='level15' else 1,level_cap=15 if profile=='level15' else None);records=[]
for number,step in enumerate(session['steps'],1):
    target=tuple(sorted(map(tuple,step['cells'])))
    route=ground_locks(tuple(step['board_before']),step['piece'],kicks,allow180=True,allow_wall=True,
        wanted=target,wanted_spin=step.get('spin','none')).get(target)
    record=dict(number=number,piece=step['piece'],strategy=step.get('strategy'),level_before=score.level,
        high_gravity=(20 if profile=='20g' else gravity(10 if profile=='level10' else 15 if profile=='level15' else score.level))>=20,ground_reachable=route is not None,
        saved_estimated_faults=step.get('estimated_finesse_faults'),
        minimum_estimated_faults=estimated_faults(step['piece'],target,route['actions']) if route else None,
        saved_actions=step['actions'],minimum_actions=route['actions'] if route else None,
        preserves_spin=step.get('spin','none'),lock_verification=step.get('lock_verification'))
    records.append(record)
    score=score.place(len(step['cleared_rows']),step.get('spin','none'),tuple(step['board_after'])==empty_board())
def group(rows):
    return dict(pieces=len(rows),ground_reachable=sum(r['ground_reachable'] for r in rows),
        saved_estimated_faults=sum(r['saved_estimated_faults'] or 0 for r in rows),
        minimum_estimated_faults=sum(r['minimum_estimated_faults'] or 0 for r in rows),
        strict_reachable=sum(r['minimum_estimated_faults']==0 for r in rows),
        shorter_estimated_routes=sum(r['ground_reachable'] and r['minimum_estimated_faults']<(r['saved_estimated_faults'] or 0) for r in rows))
intervals=[];previous_pieces=previous_faults=0
for checkpoint in checkpoints:
    stats=checkpoint['stats'];pieces=stats['piecesplaced'];faults=stats['finesse']['faults']
    interval=[r for r in records if previous_pieces<r['number']<=pieces]
    high=[r for r in interval if r['high_gravity']]
    intervals.append(dict(frame=checkpoint['frame'],native_pieces_before=previous_pieces,native_pieces_after=pieces,
        native_fault_increase=faults-previous_faults,controlled_pieces=len(interval),
        high_gravity=group(high),extra_ground_routes=[r for r in high if r['minimum_estimated_faults']],
        interpretation='Checkpoint aggregate only; it does not identify native faults for individual pieces.'))
    previous_pieces,previous_faults=pieces,faults
summary=dict(all=group(records),high_gravity=group([r for r in records if r['high_gravity']]),
    simulation_profile=profile,native_final_finesse=native['finesse'],native_pieces=native['piecesplaced'],
    native_final_source='results.stats' if replay['replay'].get('results',{}).get('stats') else 'last full checkpoint',
    native_new_run=False,future_queue_read=False,
    assumptions='Same historical cells and spin, settled spawn, ARR=0, sonic drop; saved estimates are not complete native input counts')
args.output.write_text(json.dumps(dict(summary=summary,checkpoint_intervals=intervals,steps=records),ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False))
