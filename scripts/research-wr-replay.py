"""Offline hypothesis reconstruction of a public replay, never live input.

The recorded seed is used ONLY to study this historical public performance.
Results must match native statistics and sampled boards before attribution.
"""
import json,sys,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from pc_lab.engine import empty_board,cells,fits,lock,load_kicks
from pc_lab.blitz import settle,raw_ground_action,t_spin,Score,gravity
from pc_lab.solver import ROOT

r=json.loads((ROOT/'output/blitz-world-record.ttr').read_text())['replay']
seed=r['options']['seed']%2147483647
if seed<=0:seed+=2147483646
queue=[]
for _ in range(100):
    bag=list('ZLOSIJT')
    for i in range(6,0,-1):
        seed=16807*seed%2147483647;j=int((seed-1)/2147483646*(i+1))
        bag[i],bag[j]=bag[j],bag[i]
    queue.extend(bag)
if r['options'].get('no_szo'):
    while queue[0] in 'SZO':queue.pop(0)
board=empty_board();kicks=load_kicks(ROOT/'data/srsplus90.properties')
index=1;piece=queue[0];held=None;pose=(4,21,0);spin='none';score=Score()
pressed={};last=None;fall=0.;clock=0.;steps=[];held_used=False
def spawn(p):
    global piece,pose,spin,fall
    piece=p;pose=(4,21,0);spin='none';fall=0.
def shift(dx):
    global pose,spin
    x,y,rot=pose
    if fits(board,cells(piece,rot,x+dx,y)):
        pose=(x+dx,y,rot);spin='none'
        if 'softDrop' in pressed:pose=settle(board,piece,pose)
def tick(dt):
    global pose,spin,fall
    if last in pressed and clock+dt-pressed[last]>=r['options']['handling']['das']:
        for _ in range(10):shift(-1 if last=='moveLeft' else 1)
    rate=400 if 'softDrop' in pressed else gravity(score.level)
    fall+=rate*dt
    if fall>=1:
        if fall>=24:pose=settle(board,piece,pose);fall=0.
        else:
            while fall>=1:
                x,y,rot=pose
                if fits(board,cells(piece,rot,x,y-1)):pose=(x,y-1,rot)
                fall-=1
for e in r['events']:
    if e['type'] not in ('keydown','keyup'):continue
    when=e['frame']+e['data'].get('subframe',0)
    while clock<when-1e-8:
        dt=min(.1,when-clock);tick(dt);clock+=dt
    key=e['data']['key']
    if e['type']=='keyup':
        pressed.pop(key,None)
        if key==last:last=('moveRight' if key=='moveLeft' else 'moveLeft') if ('moveRight' if key=='moveLeft' else 'moveLeft') in pressed else None
        continue
    pressed[key]=clock
    if key in ('moveLeft','moveRight'):
        last=key;shift(-1 if key=='moveLeft' else 1)
    elif key=='hold':
        old=piece
        if held is None:spawn(queue[index]);index+=1
        else:spawn(held)
        held=old;held_used=True
    elif key.startswith('rotate') and piece!='O':
        action={'rotateCW':'cw','rotateCCW':'ccw','rotate180':'cw180'}[key]
        try:
            old=pose;pose=raw_ground_action(board,piece,pose,action,kicks)
            spin=t_spin(board,piece,pose,action)
        except ValueError:pass
    elif key=='hardDrop':
        old=pose;pose=settle(board,piece,pose)
        pts=cells(piece,pose[2],pose[0],pose[1]);before=board
        try:board,placed,cleared=lock(board,pts,piece)
        except ValueError:
            print('FAILED',len(steps)+1);break
        score=score.place(len(cleared),spin,board==empty_board())
        steps.append(dict(number=len(steps)+1,piece=piece,cells=pts,board_before=before,board_after=board,
                          lines=len(cleared),spin=spin,pc=board==empty_board(),frame=when,score=score.to_dict(),hold=held))
        spawn(queue[index]);index+=1;held_used=False
summary={k:score.to_dict()[k] for k in ('level','lines','pcs','tspins','score')}
native=r['results']['stats'];summary['native']={k:native[k] for k in ('level','lines','tspins','piecesplaced')}
summary['native']['pcs']=native['clears']['allclear'];summary['pieces']=len(steps)
summary['validated_statistics']=all(summary[k]==summary['native'][k] for k in ('level','lines','pcs','tspins')) and len(steps)==native['piecesplaced']
out=ROOT/'output/wr-reconstruction-hypothesis.json';out.write_text(json.dumps(dict(summary=summary,steps=steps),indent=2),encoding='utf-8')
print(json.dumps(summary));print('PC boundaries',[(s['number'],s['score']['lines']) for s in steps if s['pc']][:15])
