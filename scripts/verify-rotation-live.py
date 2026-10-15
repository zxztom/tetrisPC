"""Bounded native regression: finish the preserved test field, no reset."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from PIL import Image
from pc_lab.live import Runner
from pc_lab.engine import cells,empty_board,load_kicks
from pc_lab.online import choose_plan
from pc_lab.solver import ROOT
from pc_lab.vision import read_state,Geometry
from pc_lab.windows import focus

source=ROOT/'output/live-20261014-001732-2a42a8c6'
record=json.loads((source/'session.json').read_text(encoding='utf-8'))
runner=Runner({'live_mode':'visible','operation_interval_ms':120},
              lambda state,message:print(state,message,flush=True))
focus(runner.hwnd)
original=read_state(Image.open(source/'start.png'))
runner.geometry=Geometry(**original['geometry'])
runner.kick_path=ROOT/'data/srsplus90.properties';runner.kicks=load_kicks(runner.kick_path)
board=tuple(record['steps'][-1]['board_after'])
state,image=runner.observe(board)
if state['board']!=board or set(map(tuple,state['active_cells']))!=set(cells(state['active'],0,4,21)):
    raise RuntimeError('Test field changed; no keys sent.')
known={0:original['active']};known.update(dict(enumerate(original['next'],1)))
held=None
for step in record['steps']:
    known[step['source_index']]=step['piece']
    if step['hold_used']:held=step['global_queue_index_before']
    current=step['global_queue_index_after']
    if step.get('observed_active_after'):
        known[current]=step['observed_active_after']
        known.update({current+i+1:p for i,p in enumerate(step['observed_next_after'])})
runner.preview_count=len(state['next'])
runner.confirm_preview(known,current,board,state['hold'])
runner.steps=list(record['steps']);runner.cleared=record['cleared_lines']
image.save(runner.folder/'start.png')
remaining=6-runner.cleared;pending=[];observed=[]
for turn in range(10):
    if not remaining:break
    if turn==4:runner.timing['operation_interval_ms']=45
    if not pending:
        pending=choose_plan(known,current,held,board,remaining,15,16,runner.stopped,
                            kick_path=runner.kick_path)
    step=dict(pending.pop(0));step['queue_index_after']-=step['queue_index_before'];step['queue_index_before']=0
    before=current;held_before=known[held] if held is not None else None;source_index=current
    if step['hold_used']:
        source_index=held if held is not None else before+1;held=before
    current+=step['queue_index_after'];held_after=known[held] if held is not None else None
    step.update(source_index=source_index,global_queue_index_before=before,
                global_queue_index_after=current,cycle=1,stage='bounded-six-line-regression')
    started=time.monotonic()
    runner.execute(step,known[before],held_before,known.get(current),held_after)
    board=tuple(step['board_after'])
    state,revealed=runner.confirm_preview(known,current,board,held_after);known.update(revealed)
    remaining-=len(step['cleared_rows'])
    observed.append({'piece':step['piece'],'target_cells':step['cells'],'actions':step['actions'],
                     'interval_ms':runner.interval_ms(),'verified_board':True,
                     'elapsed_seconds':round(time.monotonic()-started,3)})
    (runner.folder/'rotation-regression.json').write_text(json.dumps(observed,indent=2),encoding='utf-8')
if remaining or board!=empty_board():raise RuntimeError('Bounded regression did not finish; no reset.')
runner.write_status('done','六行实机旋转回归完成；未重开 ZEN，分别验证 120 / 45 毫秒间隔。')
print(str(runner.folder),flush=True)
