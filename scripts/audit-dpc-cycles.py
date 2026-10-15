"""Recount historic bot cycles from placements, without seeds or futures."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from pc_lab.loop_tracker import dpc_cycles
from pc_lab.solver import ROOT

reports=[]
for path in sorted((ROOT/'output').glob('live-*/session.json')):
    raw=json.loads(path.read_text(encoding='utf-8'))
    if raw.get('strategy')!='blitz_score' or not raw.get('steps'):continue
    steps=raw['steps'];boundaries=[];lines=0
    for number,step in enumerate(steps,1):
        lines+=len(step['cleared_rows'])
        if all(row=='__________' for row in step['board_after']):boundaries.append(dict(pieces=number,lines=lines))
    evidence=dpc_cycles(boundaries,steps)
    reports.append(dict(session=str(path),status=raw['status'],pieces=len(steps),pcs=len(boundaries),
                        old_cycles=raw.get('completed_cycles'),**evidence))
(ROOT/'output/dpc-cycle-audit.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps([{k:v for k,v in r.items() if k not in ('cycles','session')}|dict(session=Path(r['session']).parent.name)
                  for r in reports if r['old_cycles']!=r['verified_cycles']],ensure_ascii=False))
