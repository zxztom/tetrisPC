"""Find an offline scoring regression from already observed native moves."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from pc_lab.blitz import Score
from pc_lab.blitz_finish import improve_finish
from pc_lab.engine import empty_board,load_kicks
from pc_lab.finesse import estimated_faults
from pc_lab.solver import ROOT

session=json.loads((ROOT/'output/live-20261015-133329-cced7b92/session.json').read_text(encoding='utf-8'))
steps=session['steps'];known={};scores=[Score()]
for step in steps:
    known[step['source_index']]=step['piece']
    after=step['global_queue_index_after'];known[after]=step['observed_active_after']
    known.update({after+i+1:p for i,p in enumerate(step['observed_next_after'])})
    scores.append(scores[-1].place(len(step['cleared_rows']),step.get('spin','none'),tuple(step['board_after'])==empty_board()))
kicks=load_kicks(ROOT/'data/srsplus90.properties')
def result(plan,score):
    for step in plan:score=score.place(len(step['cleared_rows']),step.get('spin','none'),tuple(step['board_after'])==empty_board())
    return dict(score=score.score,faults=sum(estimated_faults(s['piece'],s['cells'],s['actions']) for s in plan))
for end in range(4,len(steps)):
    if tuple(steps[end-1]['board_after'])!=empty_board():continue
    begin=end-4;original=steps[begin:end];board=tuple(original[0]['board_before'])
    lines=sum(len(s['cleared_rows']) for s in original);current=original[0]['global_queue_index_before']
    queue=''.join(known.get(i,'?') for i in range(current,current+6))
    if '?' in queue:continue
    incumbent=[dict(s,queue_index_before=s['global_queue_index_before']-current,
                        queue_index_after=s['global_queue_index_after']-current) for s in original]
    options=dict(board=board,queue=queue,held=original[0]['hold_before'],kicks=kicks,
                 score=scores[begin],lines=lines,incumbent=incumbent,budget=.2)
    standard=improve_finish(**options);higher=improve_finish(**options,score_first=True)
    a,b=result(standard,scores[begin]),result(higher,scores[begin])
    if b['score']>a['score'] and b['faults']>a['faults']:
        keep=('piece','hold_used','hold_before','hold_after','queue_index_before','queue_index_after',
              'cells','x','y','rotation','actions','spin','board_before','board_after','cleared_rows')
        fixture=dict(board=board,queue=queue,held=original[0]['hold_before'],score=scores[begin].to_dict(),
            lines=lines,incumbent=[{k:s[k] for k in keep} for s in incumbent],standard=a,score_first=b,
            source='Only an already observed historical four-piece PC finish, no seed or unseen queue')
        (ROOT/'data/score-finish-regression.json').write_text(json.dumps(fixture,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(dict(piece_range=[begin+1,end],standard=a,score_first=b)));break
else:print('No strict score/fault tradeoff found in this historical sample.')
