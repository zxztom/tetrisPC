"""Compare an exported single-player replay with verified pixel-bot placements.

Only recorded statistics and executed moves are used; options.seed and
the recorded future queue are never read by this audit or live planning.
"""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from pc_lab.blitz import Score,settle,raw_ground_action,t_spin
from pc_lab.engine import load_kicks,empty_board,cells,poses_for,fits
from pc_lab.solver import ROOT

p=argparse.ArgumentParser()
p.add_argument('replay',type=Path);p.add_argument('session',type=Path)
p.add_argument('--output',type=Path)
a=p.parse_args();sys.stdout.reconfigure(encoding='utf-8')
replay=json.loads(a.replay.read_text(encoding='utf-8'))
session=json.loads(a.session.read_text(encoding='utf-8'))
if replay['gamemode'] not in ('custom','blitz'):raise ValueError('Audit requires a single-player score replay.')
kicks=load_kicks(ROOT/'data/srsplus90.properties')
fixed=session.get('simulation_profile')=='level15'
models=[Score(level=15 if fixed else 1,level_cap=15 if fixed else None)];adjusted=[]
for number,step in enumerate(session['steps'],1):
    board=tuple(step['board_before']);piece=step['piece'];pose=settle(board,piece,(4,21,0));spin='none'
    if step.get('correction_observations'):
        pose=poses_for(piece,step['correction_observations'][-1]['active_cells'])[0]
        if piece=='T' and len(step['actions'])==1:raise ValueError('T spin history is ambiguous after an input correction.')
    air=step.get('lock_verification')=='air_sprite_projection_before_and_board_after'
    if air:pose=tuple(step['execution_route_start'])
    elif step.get('execution_ground_start'):pose=tuple(step['execution_ground_start'])
    for action in step['actions'][:-1]:
        if air and action.endswith('_wall'):
            x,y,rotation=pose;dx=-1 if action=='left_wall' else 1
            while fits(board,cells(piece,rotation,x+dx,y)):x+=dx
            raw=(x,y,rotation)
        else:raw=raw_ground_action(board,piece,pose,action,kicks)
        after=raw if air else settle(board,piece,raw);upgrade=False
        if piece=='T' and action in ('cw','ccw'):
            offsets=kicks['T.'+'NESW'[pose[2]]+'NESW'[raw[2]]]
            delta=(raw[0]-pose[0],raw[1]-pose[1])
            upgrade=delta==offsets[4] and delta not in offsets[:4]
        spin=t_spin(board,piece,raw,action,upgrade) if not air and raw==after else 'none'
        pose=after
    if air:pose=settle(board,piece,pose)
    if tuple(sorted(map(tuple,step['cells'])))!=tuple(sorted(cells(piece,pose[2],pose[0],pose[1]))):
        raise ValueError(f'Executed route disagrees with target at piece {number}.')
    if step.get('spin','none')!=spin:adjusted.append(number)
    models.append(models[-1].place(len(step['cleared_rows']),spin,tuple(step['board_after'])==empty_board()))

checkpoints=[];errors=[]
for event in replay['replay']['events']:
    if event['type']!='full':continue
    native=event['data']['stats'];number=native['piecesplaced']
    if number>=len(models):continue
    model=models[number]
    expected=(model.level,model.level_progress,model.lines,model.pcs,model.tspins,model.b2b)
    actual=(native['level'],native['level_lines'],native['lines'],native['clears']['allclear'],native['tspins'],native['btb'])
    if expected!=actual:errors.append(dict(frame=event['frame'],pieces=number,expected=expected,actual=actual))
    checkpoints.append(dict(frame=event['frame'],pieces=number,native_score=native['score'],
                            estimated_clear_score=model.score,native_minus_clear_estimate=native['score']-model.score))
native=replay['replay']['results']['stats']
report=dict(mode=replay['gamemode'],native={k:native[k] for k in ('score','level','lines','piecesplaced','tspins','finaltime')},
            native_pcs=native['clears']['allclear'],verified_pieces=len(session['steps']),
            native_finesse=native['finesse'],native_inputs=native['inputs'],
            corrected_clear_estimate=models[-1].score,historical_spin_flags_adjusted=adjusted,
            checkpoints=checkpoints,mismatches=errors,ground_corrections=session['ground_corrections'])
if a.output:a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='checkpoints'},ensure_ascii=False))
if errors:raise SystemExit(1)
