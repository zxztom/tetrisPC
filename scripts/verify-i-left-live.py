"""One-piece native I regression; preserves the current ZEN field."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8')
from PIL import Image
from pc_lab.live import Runner
from pc_lab.engine import cells,empty_board,lock,load_kicks,preferred_route
from pc_lab.solver import ROOT
from pc_lab.vision import read_state,Geometry
from pc_lab.windows import focus

source=ROOT/'output/live-20261014-002348-88e92892'
record=json.loads((source/'session.json').read_text(encoding='utf-8'))
runner=Runner({'live_mode':'visible','operation_interval_ms':45},
              lambda state,message:print(state,message,flush=True))
focus(runner.hwnd)
original=read_state(Image.open(source/'start.png'))
runner.geometry=Geometry(**original['geometry'])
runner.kick_path=ROOT/'data/srsplus90.properties';runner.kicks=load_kicks(runner.kick_path)
expected=tuple(record['steps'][-1]['board_after'])
state,image=runner.observe(expected)
if state['board']!=expected and state['board']!=empty_board():raise RuntimeError('Field changed; no keys sent.')
if state['active']!='I' or set(map(tuple,state['active_cells']))!=set(cells('I',0,4,21)):
    raise RuntimeError('Active piece is not a spawn I; no keys sent.')
before=state['board'];target=[(0,y) for y in range(4)]
route=preferred_route(before,'I',target,runner.kicks)
assert 'soft_drop' not in route['actions']
after,placed,cleared=lock(before,target,'I')
step={'piece':'I','hold_used':False,'hold_before':state['hold'],'hold_after':state['hold'],
      'cells':target,'board_before':before,'board_placed':placed,'board_after':after,'cleared_rows':cleared,**route}
image.save(ROOT/'output/native-i-left-before.png')
runner.execute(step,'I',state['hold'],after_hold=state['hold'])
state,image=runner.observe(after);assert state['board']==after
image.save(ROOT/'output/native-i-left-after.png')
timings=step['input_timing'];gaps=[(b['started']-a['released'])*1000 for a,b in zip(timings,timings[1:])]
result={'status':'verified','native_mode':'ZEN','rotation_rules':'SRS+90','target_column':0,
        'target_cells':target,'actual_board_verified':True,'actions':step['actions'],'interval_ms':45,
        'minimum_measured_gap_ms':round(min(gaps),2),'reset':False,'output_directory':str(runner.folder)}
(ROOT/'output/native-i-left-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
runner.write_status('done','I 块已在空中旋转并落入最左列，实际落地棋盘已核对。')
print(json.dumps(result),flush=True)
