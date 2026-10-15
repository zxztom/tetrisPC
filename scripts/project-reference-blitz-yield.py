"""Offline scoring scenarios, not replay simulation or an online queue source."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from pc_lab.blitz import Score
from pc_lab.solver import ROOT

reference=json.loads((ROOT/'output/wr-reconstruction-hypothesis.json').read_text(encoding='utf-8'))
assert reference['summary']['validated_statistics']
steps=reference['steps']
def evaluate(events):
    state=Score();level_sum=0
    for event in events:
        level_sum+=state.level
        state=state.place(event['lines'],event['spin'],event['pc'])
    return state,level_sum

base,base_levels=evaluate(steps)
native=json.loads((ROOT/'output/blitz-world-record.ttr').read_text(encoding='utf-8'))['replay']['results']['stats']
assert (len(steps),base.lines,base.pcs,base.tspins,base.score)==(607,242,51,47,2520150)
closed_end=max(i+1 for i,e in enumerate(steps) if e['pc'])
closed=steps[:closed_end];target=749;extra=target-closed_end
assert closed_end==605
starts=[0]+[i+1 for i,e in enumerate(closed[:-1]) if e['pc']]
scenarios=[]
for start in starts:
    state,levels=evaluate(closed+[closed[(start+i)%closed_end] for i in range(extra)])
    # Per-level, per-piece drop yield held equal to the historical reference.
    # This is explicitly a scaling assumption, not a drop path simulation.
    drop=(native['score']-base.score)*levels/base_levels
    scenarios.append(dict(continuation_starts_at_historical_piece=start+1,
                          clear_score=state.score,estimated_drop_points=drop,
                          projected_score=state.score+drop,pcs=state.pcs,tspins=state.tspins,
                          lines=state.lines,level=state.level))
result=dict(reference_replay='f8f1af8afc4d',reference_native_score=native['score'],
            reference_pieces=607,target_pieces=target,target_pps=target/120,
            reference_clear_score=base.score,reference_drop_points=native['score']-base.score,
            reference_finish_seconds_at_target_speed=607/(target/120),
            simple_linear_score=native['score']*target/607,
            historical_prefix_projection=scenarios[0],
            scenario_min=min(x['projected_score'] for x in scenarios),
            scenario_max=max(x['projected_score'] for x in scenarios),scenarios=scenarios,
            limitations=['Same reference clear-yield quality AND same 749-piece speed assumed.',
                         'Continuation is synthetic score events from historical PC segments.',
                         'No claim of same seed, legal bag/Hold joins, geometry or timed reachability.',
                         'Scenario range is not a confidence interval or a theoretical upper bound.',
                         'Reference geometry reconstruction matches native totals; not a new native replay.',
                         'Drop points are extrapolated by the sum of scoring levels per piece.',
                         'No source data is passed to online planning.'])
(ROOT/'output/reference-luck-score-projection.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='scenarios'},ensure_ascii=False,indent=2))
