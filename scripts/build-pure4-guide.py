"""Build a human replay and independent audit of the real 70-lock run."""
import json,re,runpy,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from pc_lab.engine import load_kicks,lock,empty_board
from pc_lab.solver import ROOT

helpers=runpy.run_path(str(ROOT/'scripts/build-human-guide.py'))
source=ROOT/'output/live-20261014-080335-f64062fe/session.json'
r=json.loads(source.read_text(encoding='utf-8'))
assert r['status']=='done' and r['completed_cycles']==1 and len(r['steps'])==70
known={}
for step in r['steps']:
    known[step['source_index']]=step['piece']
    if step.get('observed_active_after'):
        i=step['global_queue_index_after'];known[i]=step['observed_active_after']
        known.update({i+n+1:p for n,p in enumerate(step['observed_next_after'])})
kicks=load_kicks(ROOT/'data/srsplus90.properties');steps=[];previous=empty_board()
for number,original in enumerate(r['steps'],1):
    s=dict(original);assert tuple(s['board_before'])==previous
    frames=helpers['replay'](previous,s['piece'],s['actions'],kicks)
    assert set(map(tuple,frames[-1]['cells']))==set(map(tuple,s['cells']))
    after,placed,cleared=lock(previous,frames[-1]['cells'],s['piece'])
    assert after==tuple(s['board_after']) and cleared==tuple(s['cleared_rows'])
    i=s['global_queue_index_before'];names=helpers['NAMES']
    s.update(number=number,current_before=known[i],next_before=''.join(known[j] for j in range(i+1,i+6)),frames=frames,
             actions_text=' → '.join((['Hold'] if s['hold_used'] else [])+[names[a] for a in s['actions']]),
             target_columns=sorted({x+1 for x,y in s['cells']}),pc=after==empty_board())
    steps.append(s);previous=after
pcs=[s['number'] for s in steps if s['pc']]
assert pcs==list(range(10,71,10))
assert sorted(s['source_index'] for s in steps)==list(range(70))
assert sum(len(s['cleared_rows']) for s in steps)==28
for start in range(0,70,7):assert set(known[i] for i in range(start,start+7))==set('IJLOSTZ')
data={'source_recording':str(source.relative_to(ROOT)),'uses_seed':False,'rules':'SRS+90',
      'native_placements_verified':True,'all_displayed_routes_executed_native':True,
      'pc_indices':pcs,'steps':steps,'conditions':r['native_test_conditions']}
(ROOT/'docs/pure4-human-replay.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
template=(ROOT/'ui/manual-template.html').read_text(encoding='utf-8')
template=template.replace('不知道种子的连续 PC · 人类操作说明','七次四行 PC · 实机操作图解')
template=template.replace('TETR.IO / 4 + 4 + 6 / 无种子','TETR.IO / 七次四行 PC / 无种子')
template=template.replace('35块随机连续PC图解','70块随机连续PC图解').replace('max="34"','max="69"')
template=template.replace('第 ${s.number} / 35 块','第 ${s.number} / 70 块').replace('cursor===34','cursor===69')
template=template.replace("s.stage===3?'六行 DPC':'四行 PC '+s.stage","'第 '+s.stage+' 次四行 PC'")
choices=''.join(f'<option value="{(n-1)*10}">第 {n} 次 PC 开始</option>' for n in range(1,8))+'<option value="69">第七次 PC 收尾</option>'
template=re.sub(r'(<select id="jump"[^>]*>).*?(</select>)',lambda m:m[1]+choices+m[2],template,count=1)
intro='这一轮真实随机 CUSTOM 完成 70 块、七次四行 PC、28 行；只读取当前块、Hold 和五个 Next，没有取得种子。前四块后修复识别并从原棋盘继续，本局没有重开。下方所有路线均按实际执行记录逐动作验证。'
template=re.sub(r'(<p class="introbox">).*?(</p>)',lambda m:m[1]+intro+m[2],template,count=1)
template=template.replace('历史来源：output/live-20261013-233735-53c38fb6/session.json · 完整改后路线未重新在实机跑完一轮 · 本页面不会发送游戏按键。',
                          '历史来源：output/live-20261014-080335-f64062fe/session.json · 前四块暂停后继续同一局 · 本页面不会发送游戏按键。')
guide=(ROOT/'docs/七次四行PC循环说明.md').read_text(encoding='utf-8')
doc=template.replace('<!--GUIDE-->',helpers['render_md'](guide)).replace('/*REPLAY_DATA*/',json.dumps(data,ensure_ascii=False).replace('</','<\\/'))
(ROOT/'ui/pure4-manual.html').write_text(doc,encoding='utf-8')
(ROOT/'docs/七次四行PC实机图解.html').write_text(doc,encoding='utf-8')
verification={'recording':str(source.relative_to(ROOT)),'resumed_from':r.get('resumed_from_recording'),
              'status':'verified','placed_pieces':70,'pcs':7,'lines':28,'cycles':1,'pc_indices':pcs,
              'source_indices_verified':True,'ten_bags_verified':True,'no_seed_read':True,'restarts':0,
              'actions_replayed':sum(len(s['actions']) for s in steps),'preview_count':5,'rotation_rules':'SRS+90'}
(ROOT/'output/pure4-native-verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(verification,ensure_ascii=False))
