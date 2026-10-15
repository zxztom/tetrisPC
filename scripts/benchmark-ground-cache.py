"""Replay historical geometric queries only; no game input, seed or queue."""
import argparse,json,statistics,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from pc_lab.blitz import ground_locks,_ground_locks_uncached,clear_ground_cache,ground_cache_info
from pc_lab.engine import load_kicks
from pc_lab.solver import ROOT

p=argparse.ArgumentParser()
p.add_argument('--session',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
args=p.parse_args();session=json.loads(args.session.read_text(encoding='utf-8'))
kicks=load_kicks(ROOT/'data/srsplus90.properties');queries=[]
for step in session['steps']:
    board=tuple(step['board_before']);target=tuple(sorted(map(tuple,step['cells'])))
    start=step.get('execution_ground_start')
    if start is None:continue
    spin=step.get('spin') if step.get('spin')!='none' else None
    # Actual ground placement query, duplicated to represent planning then
    # execution. This isolates repeated geometry; it is NOT a live PPS test.
    query=dict(board=board,piece=step['piece'],kicks=kicks,start=tuple(start),
               wanted=target,wanted_spin=spin,allow180=session['allow180'],allow_wall=True)
    queries.extend([query,query])
clear_ground_cache();times={};expected=[]
for name,fn in [('uncached',_ground_locks_uncached),('cached',ground_locks)]:
    durations=[]
    for number,query in enumerate(queries):
        began=time.perf_counter();result=fn(**query);durations.append(time.perf_counter()-began)
        if name=='uncached':expected.append(result)
        elif result!=expected[number]:raise RuntimeError('Cache changed route geometry/actions/spin')
    times[name]=dict(total_ms=1000*sum(durations),mean_ms=1000*statistics.mean(durations),
                     maximum_ms=1000*max(durations))
report=dict(session=str(args.session),queries=len(queries),timing=times,cache=ground_cache_info(),
            all_results_identical=True,native_test=False,execution_and_vision_included=False,
            scenario='Two identical queries per historical ground placement; not whole live planner timing.')
args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
