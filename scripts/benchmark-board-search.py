"""Historical geometry/visible inputs only; never a live queue source."""
import argparse,json,statistics,sys,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from pc_lab.blitz import board_cost,_ground_locks_uncached
from pc_lab.engine import lock,load_kicks
from pc_lab.solver import ROOT
from tests.test_sparse_board import reference_cost,reference_lock

p=argparse.ArgumentParser();p.add_argument('--session',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
a=p.parse_args();session=json.loads(a.session.read_text(encoding='utf-8'))
steps=session['steps'];kicks=load_kicks(ROOT/'data/srsplus90.properties');report={'source':str(a.session),'native_test':False}
for name,fn,old,args in [('board_cost',board_cost,reference_cost,[(tuple(s['board_after']),) for s in steps]),
                       ('lock',lock,reference_lock,[(tuple(s['board_before']),tuple(map(tuple,s['cells'])),s['piece']) for s in steps])]:
    assert all(fn(*v)==old(*v) for v in args)
    times={}
    for label,f in [('before',old),('after',fn)]:
        rounds=[]
        for _ in range(7):
            began=time.perf_counter()
            for _ in range(10):
                for v in args:f(*v)
            rounds.append(1000*(time.perf_counter()-began))
        times[label]=statistics.median(rounds)
    report[name]={'calls':len(args)*10,'median_ms':times,'identical':True}
queries=[dict(board=tuple(s['board_before']),piece=s['piece'],kicks=kicks,
              allow180=True,allow_wall=True) for s in steps[::4]]
expected=[_ground_locks_uncached(**q,fast_geometry=False) for q in queries]
assert all(_ground_locks_uncached(**q)==v for q,v in zip(queries,expected))
times={}
for label,fast in [('before',False),('after',True)]:
    rounds=[]
    for _ in range(5):
        began=time.perf_counter()
        for q in queries:_ground_locks_uncached(**q,fast_geometry=fast)
        rounds.append(1000*(time.perf_counter()-began))
    times[label]=statistics.median(rounds)
report['ground_routes']={'queries':len(queries),'median_ms':times,'identical':True,'geometry_cache_used':False}
a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
