"""Build a finite offline PC lesson. Never supplies moves to a live game."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from pc_lab.best_fields import fields
from pc_lab.engine import empty_board,load_kicks,reconstruct
from pc_lab.fast_solver import find_pc
from pc_lab.search_worker import close_worker
from pc_lab.finesse import estimated_faults
from pc_lab.solver import ROOT

queue='IOSJTZLJLOSTZI';held='I';kicks=load_kicks(ROOT/'data/srsplus90.properties')
field=next(f for f in fields() if f['phase']==3 and f['signature']=='IISO')
physical=tuple(r for r in reversed(field['rows']) if '_' in r)
goal=physical+empty_board()[len(physical):]
ops=[dict(piece=o['piece'],original_cells=tuple(map(tuple,o['original_cells']))) for o in field['operations'][0]]
setup=reconstruct(ops,empty_board(),queue[:4],held,True,kicks,'ground180fine',final_board=goal)
assert setup and len(setup)==4
offset=setup[-1]['queue_index_after']
try:
    result=find_pc(queue[offset:],hold=setup[-1]['hold_after'],rows=list(reversed(goal[:3])),lines=3,
        mode='soft',path_mode='ground180fine',persistent=True,timeout=1.5,
        kick_path=ROOT/'data/srsplus90.properties',save=False)
    assert result['status']=='solved'
finally:close_worker()
steps=[]
names={'left':'左移一格','right':'右移一格','left_wall':'向左按住到不能再移动','right_wall':'向右按住到不能再移动',
       'cw':'顺转90°','ccw':'逆转90°','cw180':'转180°','hard_drop':'硬降'}
for n,step in enumerate(setup+result['steps'],1):
    step=dict(step);base=0 if n<=4 else offset
    index=base+step['queue_index_before'];after_index=base+step['queue_index_after']
    steps.append(dict(step,number=n,current_before=queue[index],next_before=queue[index+1:index+7],
        actions_text=' → '.join((['Hold取'+step['piece']] if step['hold_used'] else [])+[names[a] for a in step['actions']]),
        pc=tuple(step['board_after'])==empty_board(),next_active=queue[after_index],
        estimated_faults=estimated_faults(step['piece'],step['cells'],step['actions'])))
assert len(steps)==10 and sum(len(s['cleared_rows']) for s in steps)==4 and steps[-1]['pc']
assert sum(s['estimated_faults'] for s in steps)==0
data=dict(steps=steps,offline_example=True,native_run=False,seed_used=False,
          source_image=field['source_image'],reported_coverage_is_native_success=False)
(ROOT/'output/setup-clear-guide-example.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
style=(ROOT/'ui/manual-template.html').read_text(encoding='utf-8').split('<style>',1)[1].split('</style>',1)[0]
page='''<!doctype html><html lang="zh-CN"><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>先消一行，再完成四行PC · 十块图解</title><style>__STYLE__</style><main>
<div class="tag">离线可复现实例 · 非实机成绩</div><h1>先消一行，再完成四行 PC</h1>
<p class="introbox">空场、Hold I，当前及六个Next为 I O S J T Z L。前四步只用这些已知块。后续实际出现 T Z L J L O 时，才能照本例收尾；别的队列须重新选分支，不需要设种子。</p>
<p>按SRS+、ARR=0、软降到底后的地面操作验证。按住方向到不能继续移动，可能被堆栈挡住。<a href="/">返回工具</a> · <a href="/manual">连续PC说明</a></p>
<section class="replay" aria-label="十块四行PC图解"><div class="controls"><b id="stepLabel"></b>
<select id="jump" aria-label="跳转步骤"><option value="0">开始搭建</option><option value="2">第3块先消一行</option><option value="3">四块搭建结束</option><option value="9">第10块全清</option></select></div>
<div class="facts"><div>操作前当前块<br><b id="current"></b></div><div>Hold前 → 后<br><b id="hold"></b></div><div>Next（近 → 远）<br><span id="nextPieces"></span></div></div>
<div id="actions" class="actions"></div><p id="cost" class="note"></p>
<div class="states"><div><h3>① 操作前 · 白框为目标</h3><canvas id="before" width="300" height="240" role="img"></canvas></div><div><h3>② 锁定后 · 消行前</h3><canvas id="placed" width="300" height="240" role="img"></canvas></div><div><h3>③ 消行后</h3><canvas id="after" width="300" height="240" role="img"></canvas></div></div>
<p id="checkpoint"></p><div class="controls"><button id="prev">上一块</button><input id="timeline" type="range" min="0" max="9" value="0" aria-label="选择第几块"><button id="next">下一块</button></div></section>
<article class="guide"><h2>为什么不是再放十块？</h2><p>前四块合计16格，先消一行后只剩6格。四行目标已完成1行，还需3行，因此剩余空格为30−6=24，只需再放6块。图中I、O被消行切开的残留仍合法。</p>
<h2>公共覆盖率与真实操作</h2><p>导入器曾丢弃含满行的13个合法布局，现已恢复并按实际消行更新目标棋盘。资料里的100%不保证20G地面可搭成；每个布局仍须验证当前块顺序、Hold和路线。</p>
<p><a href="https://knewjade.github.io/best-chance-field/">knewjade原始地形资料</a>。这里十块、四行全清和0估计额外输入均经离线求解器验证；真实原生finesse、速度及两分钟稳定性没有在本例验证。此页面不会发送游戏按键。</p></article></main><script>
const replay=__DATA__;const colors={I:'#55dce2',J:'#5982ef',L:'#f5a450',O:'#f4d95a',S:'#9ee653',T:'#af7aec',Z:'#ef6d80'};
let cursor=0;const $=id=>document.getElementById(id);
function board(id,rows,points=[]){const c=$(id),ctx=c.getContext('2d'),size=c.width/10;ctx.clearRect(0,0,c.width,c.height);for(let y=0;y<8;y++)for(let x=0;x<10;x++){const px=x*size,py=(7-y)*size;ctx.strokeStyle='#253847';ctx.lineWidth=.7;ctx.strokeRect(px+.5,py+.5,size-1,size-1);const p=rows[y][x];if(p!=='_'){ctx.fillStyle=colors[p]||'#617b8c';ctx.fillRect(px+2,py+2,size-4,size-4);}}for(const[x,y]of points){if(y>=8)continue;ctx.strokeStyle='#f2ffff';ctx.lineWidth=2;ctx.strokeRect(x*size+3,(7-y)*size+3,size-6,size-6);}c.setAttribute('aria-label',id+'棋盘：列从左到右1至10，行从下到上');}
function draw(){const s=replay.steps[cursor];$('stepLabel').textContent=`第 ${s.number} / 10 块 · ${s.number<=4?'搭建地形':'剩余三行收尾'}`;$('current').textContent=s.current_before;$('current').style.color=colors[s.current_before];$('hold').textContent=(s.hold_before||'空')+' → '+(s.hold_after||'空');$('nextPieces').replaceChildren(...[...s.next_before].map(p=>{const el=document.createElement('span');el.className='chip';el.textContent=p;el.style.background=colors[p];return el;}));$('actions').textContent=s.actions_text;$('cost').textContent=`本步放置 ${s.piece} · 估计额外参考输入 ${s.estimated_faults} · 先软降到底，再按所列动作执行`;
board('before',s.board_before,s.cells);board('placed',s.board_placed,s.cells);board('after',s.board_after);
const lines=replay.steps.slice(0,cursor+1).reduce((n,s)=>n+s.cleared_rows.length,0);$('checkpoint').className=s.pc?'pc':'note';$('checkpoint').textContent=s.pc?`全清 ✓ · 10块累计消4行 · 留下Hold ${s.hold_after}`:`本步消 ${s.cleared_rows.length} 行 · 累计 ${lines} 行 · 下一当前 ${s.next_active}`;$('timeline').value=cursor;$('prev').disabled=cursor===0;$('next').disabled=cursor===9;}
$('prev').onclick=()=>{cursor--;draw();};$('next').onclick=()=>{cursor++;draw();};$('timeline').oninput=e=>{cursor=Number(e.target.value);draw();};$('jump').onchange=e=>{cursor=Number(e.target.value);draw();};draw();
</script></html>'''
page=page.replace('__STYLE__',style).replace('__DATA__',json.dumps(data,ensure_ascii=False).replace('</','<\\/'))
(ROOT/'ui/setup-clears.html').write_text(page,encoding='utf-8')
print('Offline lesson verified: 10 pieces, 4 lines, 0 estimated extra inputs')
