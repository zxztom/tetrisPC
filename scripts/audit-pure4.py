"""Bounded random-data audit. Planner only receives current + five Next.

Simulator queues are random test fixtures, not read from the game or
passed in full to the planner. No fixed seed is used to generate them.
"""
import argparse,json,random,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from pc_lab.engine import empty_board,load_kicks
from pc_lab.solver import ROOT
from pc_lab.online import choose_plan,observation_consistent
from pc_lab.best_fields import field_setups
from pc_lab.openers import pco_setup


def audit(queue,use_fields=True,samples=8):
    known=dict(enumerate(queue[:6]));current=0;held=None;board=empty_board();steps=[]
    known[6]=next(iter(set('IJLOSTZ')-set(known.values())))
    for phase in range(1,8):
        setups=field_setups(known,current,held,phase,KICKS) if use_fields else []
        pending=list(setups[0] if setups else (pco_setup(known,current,held,0,kicks=KICKS) if phase==1 else []) or [])
        if not setups and len(pending)==7:pending=[]
        remaining=4;count=0
        while remaining:
            if not pending:pending=choose_plan(known,current,held,board,remaining,70,samples,kick_path=KICK_PATH)
            step=dict(pending.pop(0));delta=step['queue_index_after']-step['queue_index_before'];before=current;source=current
            if step['hold_used']:
                if held is None:source=current+1;held=current
                else:source,held=held,current
            current+=delta
            step.update(stage=phase,source_index=source,global_queue_index_before=before,global_queue_index_after=current)
            steps.append(step);board=tuple(step['board_after']);remaining-=len(step['cleared_rows']);count+=1
            actual={i:queue[i] for i in range(current,current+6)}
            if not observation_consistent(known,actual):raise AssertionError('Bag or queue mismatch')
            known.update(actual)
            if board==empty_board() and remaining:raise RuntimeError('Premature PC')
        assert count==10
        print('PC',phase,'pieces',len(steps),flush=True)
    assert sorted(s['source_index'] for s in steps)==list(range(70))
    return steps


KICK_PATH=ROOT/'data/srsplus90.properties';KICKS=load_kicks(KICK_PATH)
parser=argparse.ArgumentParser();parser.add_argument('--count',type=int,default=3);parser.add_argument('--samples',type=int,default=8)
parser.add_argument('--fixtures',type=Path);parser.add_argument('--baseline',action='store_true');args=parser.parse_args()
if args.fixtures:queues=json.loads(args.fixtures.read_text(encoding='utf-8'))
else:
    rng=random.SystemRandom();queues=[''.join(''.join(rng.sample('IJLOSTZ',7)) for _ in range(12)) for _ in range(args.count)]
    (ROOT/'output/pure4-audit-fixtures.json').write_text(json.dumps(queues),encoding='utf-8')
results=[]
for i,queue in enumerate(queues[:args.count]):
    started=time.monotonic()
    try:
        steps=audit(queue,not args.baseline,args.samples)
        result={'case':i,'status':'solved','steps':steps,'uses_seed':False,'preview_count':5,'queue_test_fixture':queue}
    except Exception as exc:result={'case':i,'status':'failed','reason':str(exc),'queue_test_fixture':queue}
    result['elapsed_seconds']=round(time.monotonic()-started,2);results.append(result)
    print(json.dumps({k:v for k,v in result.items() if k!='steps'}),flush=True)
    (ROOT/('output/pure4-audit-'+('baseline' if args.baseline else 'best-fields')+'.json')).write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
