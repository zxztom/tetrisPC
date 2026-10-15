import json,random,time,argparse
from pc_lab.engine import empty_board
from pc_lab.online import choose_plan
from pc_lab.openers import pco_setup,dpc_setup

def audit(seed,generic=False):
 rng=random.Random(seed);q=''.join(''.join(rng.sample('IJLOSTZ',7)) for _ in range(6))
 known={i:p for i,p in enumerate(q[:7])};current=0;held=None;board=empty_board();steps=[]
 for number,lines in enumerate((4,4,6),1):
  prefix=list((pco_setup(known,current,held,0) if number==1 and not generic else dpc_setup(known,current,held,0) if number==3 else None) or [])
  if number==1 and len(prefix)==7:prefix=[]
  remaining=lines
  while remaining:
   if not prefix:
    try:prefix=choose_plan(known,current,held,board,remaining,35,samples=8)
    except Exception as exc:raise RuntimeError(f'stage={number}, pieces={len(steps)}, current={current}, queue={q}, reason={exc}') from exc
   s=dict(prefix.pop(0));s['queue_index_after']-=s['queue_index_before'];s['queue_index_before']=0
   source=current
   if s['hold_used']:
    if held is None:source=current+1;held=current
    else:source,held=held,current
   current+=s['queue_index_after'];steps.append(source)
   board=tuple(s['board_after']);remaining-=len(s['cleared_rows'])
   known.update({i:q[i] for i in range(current,min(current+7,len(q)))})
 assert sorted(steps)==list(range(35)) and board==empty_board()
 return {'seed_for_test_data_only':seed,'status':'solved','pieces':len(steps),'queue':q}
parser=argparse.ArgumentParser();parser.add_argument("--generic",action="store_true");parser.add_argument("--count",type=int,default=10);args=parser.parse_args()
results=[]
for seed in range(args.count):
 try:r=audit(seed,args.generic)
 except Exception as exc:r={'seed_for_test_data_only':seed,'status':'failed','reason':str(exc)}
 results.append(r);print(json.dumps(r,ensure_ascii=False),flush=True)
open('output/random-preview-'+('generic' if args.generic else 'pco')+'-audit.json','w',encoding='utf-8').write(json.dumps(results,ensure_ascii=False,indent=2))
