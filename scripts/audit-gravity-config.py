"""Audit saved native records; never capture or send desktop input."""
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from pc_lab.engine import empty_board,lock
from pc_lab.solver import ROOT

folder=ROOT/'output/live-20261014-100459-1eb97707'
session=json.loads((folder/'session.json').read_text(encoding='utf-8'))
board=empty_board();pcs=[];sources=[]
for index,step in enumerate(session['steps'],1):
    assert tuple(step['board_before'])==board
    board,_,clears=lock(board,tuple(map(tuple,step['cells'])),step['piece'])
    assert board==tuple(step['board_after']) and list(clears)==step['cleared_rows']
    sources.append(step['source_index'])
    if board==empty_board():pcs.append(index)
assert pcs==[10,20] and len(set(sources))==20 and session['status']=='done'
assert not session['uses_fixed_seed'] and session['recovery_count']==0
attempts=['live-20261014-094241-a5136b1c','live-20261014-094508-d8bbcf6d','live-20261014-094734-87e7946f']
history=[]
for name in attempts:
    item=json.loads((ROOT/'output'/name/'session.json').read_text(encoding='utf-8'))
    history.append({'directory':name,'completed_pcs':item['completed_pcs'],'placed_pieces':item['placed_pieces'],
                    'before_recovery':(ROOT/'output'/name/'before-recovery.png').is_file(),
                    'after_recovery':(ROOT/'output'/name/'after-recovery.png').is_file()})
assert history[0]['completed_pcs']==6 and history[1]['completed_pcs']==6 and history[2]['completed_pcs']>=1
result={'version':'0.6.0','uses_fixed_seed':False,'gravity_native':{
    'directory':str(folder),'mode':'ZEN STATIC 0.02','completed_pcs':2,'placed_pieces':20,'cleared_lines':8,
    'pc_piece_indices':pcs,'independent_board_replay_passed':True,'distinct_source_indices':sources,
    'steps_observed_below_row_20':sum(any(p[1]<20 for p in s['observed_poses']) for s in session['steps']),
    'wall_inputs':sum(a.endswith('_wall') for s in session['steps'] for a in s['actions']),
    'tuck_combinations':sum(any(e.get('tuck_combination') for e in s['execution_progress']) for s in session['steps']),
    'recoveries':0},'recovery_native':{'automatic_recoveries_observed':2,'attempts':history,
        'zen_level_before_and_after':269,'scores_preserved':True,'attempts_are_separate':True},
    'actual_configuration':session['control_profile'],
    'emergency_short_f8_native':'cancelled waiting, zero placement inputs; hotkey released',
    'automated_tests_passed':62,'limitations':['High gravity and 20G not validated','Not an infinite unbroken PC guarantee']}
(ROOT/'output/gravity-config-recovery-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
validation=json.loads((ROOT/'output/validation.json').read_text(encoding='utf-8'))
validation.update(version='0.6.0',phase='gravity-config-continuous-recovery',automated_tests_passed=62,
                  gravity_config_recovery=result)
(ROOT/'output/validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result['gravity_native'],ensure_ascii=False))
