"""Historic geometry audit only; does not load replay options or queues."""
import json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from pc_lab.blitz import ground_locks,Score
from pc_lab.engine import load_kicks
from pc_lab.finesse import estimated_faults
from pc_lab.solver import ROOT

steps=json.loads((ROOT/'output/wr-reconstruction-hypothesis.json').read_text(encoding='utf-8'))['steps']
kicks=load_kicks(ROOT/'data/srsplus90.properties');results=[];score=Score()
for step in steps:
    target=tuple(sorted(map(tuple,step['cells'])))
    routes=ground_locks(tuple(step['board_before']),step['piece'],kicks,allow180=True,allow_wall=True,
                        wanted=target,wanted_spin=step['spin'] if step['spin']!='none' else None)
    route=routes.get(target)
    results.append(dict(number=step['number'],piece=step['piece'],spin=step['spin'],level_before=score.level,
                        ground_reachable=route is not None,minimum_estimated_faults=estimated_faults(step['piece'],target,route['actions']) if route else None,
                        actions=route['actions'] if route else None))
    score=score.place(step['lines'],step['spin'],step['pc'])
summary=dict(pieces=len(results),reachable=sum(r['ground_reachable'] for r in results),
             zero_budget=sum(r['minimum_estimated_faults']==0 for r in results),
             extra_budget=sum(r['minimum_estimated_faults'] or 0 for r in results),
             native_wr_faults=13,assumption='All pieces start settled at spawn orientation; not native event timing proof')
high=[r for r in results if r['level_before']>8]
summary['level9_plus']=dict(pieces=len(high),reachable=sum(r['ground_reachable'] for r in high),
                            zero_budget=sum(r['minimum_estimated_faults']==0 for r in high),
                            extra_budget=sum(r['minimum_estimated_faults'] or 0 for r in high),
                            unreachable_piece_numbers=[r['number'] for r in high if not r['ground_reachable']])
(ROOT/'output/wr-ground-finesse-audit.json').write_text(json.dumps(dict(summary=summary,steps=results),ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False))
