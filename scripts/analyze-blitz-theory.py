"""Reproducible score arithmetic; reads only own executed steps and result stats."""
import argparse
import json
import sys
from html import escape
from math import ceil
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from pc_lab.blitz import Score,level_lines
from pc_lab.blitz_bounds import score_envelope,level_at
from pc_lab.solver import ROOT


def decomposition(session,audit):
    if audit['mismatches'] or audit['historical_spin_flags_adjusted']:
        raise ValueError('Use an audited session with unambiguous spin flags.')
    state=Score();parts=dict(pc=0,normal=0,spin=0,b2b=0,combo=0);counts={}
    for step in session['steps']:
        n=len(step['cleared_rows']);spin=step.get('spin','none')
        pc=all(row=='__________' for row in step['board_after'])
        base=((400,800,1200,1600)[n] if spin=='full' else
              (100,200,400,800)[n] if spin=='mini' else (0,100,300,500,800)[n])
        parts['spin' if spin!='none' else 'normal']+=base*state.level
        if n and (n==4 or spin!='none') and state.b2b:parts['b2b']+=base//2*state.level
        if n:parts['combo']+=50*state.combo*state.level
        if pc:parts['pc']+=3500*state.level
        counts[f'{spin}_{n}']=counts.get(f'{spin}_{n}',0)+1
        state=state.place(n,spin,pc)
    assert sum(parts.values())==state.score==audit['corrected_clear_estimate']
    assert (state.level,state.lines,state.pcs,state.tspins)==(
        audit['native']['level'],audit['native']['lines'],audit['native_pcs'],audit['native']['tspins'])
    parts['drop_and_nonclearing_tail']=audit['native']['score']-state.score
    assert parts['drop_and_nonclearing_tail']>=0
    return dict(native=audit['native'],pcs=state.pcs,components=parts,event_counts=counts,
                controlled_pieces=len(session['steps']),clear_score=state.score,
                pc_average_scoring_level=parts['pc']/(3500*state.pcs))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--session',type=Path,default=ROOT/'output/live-20261015-201809-011c0dd0/session.json')
    p.add_argument('--audit',type=Path,default=ROOT/'output/blitz-throughput-run3-audit.json')
    args=p.parse_args()
    actual=decomposition(json.loads(args.session.read_text(encoding='utf-8')),
                         json.loads(args.audit.read_text(encoding='utf-8')))
    modes={'446':(4,4,6),'pure4':(4,)*7};rows=[]
    for n in (600,666,720,749,780,840,960):
        row=dict(pieces=n,pps=n/120,max_lines=n*4//10,max_level=level_at(n*4//10))
        for name,cycle in modes.items():
            plain=score_envelope(n,False,cycle);bonus=score_envelope(n,True,cycle)
            row[name]=dict(pcs=bonus['pcs'],plain_min=plain['min_score'],plain_max=plain['max_score'],
                           relaxed_max=bonus['max_score'],lines_min=bonus['lines_min'],lines_max=bonus['lines_max'])
        rows.append(row)
    levels=[]
    for level in range(15,21):
        lines=sum(level_lines(i) for i in range(1,level));n=ceil(2.5*lines)
        levels.append(dict(level=level,lines=lines,minimum_pieces=n,minimum_pps=n/120))
    thresholds=[]
    for name,cycle in modes.items():
        for target in (2600000,3000000,4000000):
            low,high=0,1500
            while low<high:
                mid=(low+high)//2
                if score_envelope(mid,False,cycle)['min_score']>=target:high=mid
                else:low=mid+1
            thresholds.append(dict(mode=name,target=target,pieces=low,pps=low/120))
    result=dict(seconds=120,actual=actual,rows=rows,levels=levels,plain_envelope_thresholds=thresholds,
                source_session=str(args.session),source_audit=str(args.audit),
                assumptions=['Uninterrupted specified PC boundaries; no extra PCs.',
                             'Whole seven-bag cycles and same Hold inventory at each cycle boundary.',
                             'Cell conservation, per-cycle T stock, native levels/B2B/combo.',
                             'No tetromino geometry, ordered bag realization, SRS or input timing proof.',
                             'Envelope excludes soft/hard drop points; it is not a guaranteed playable score.'])
    (ROOT/'output/blitz-theory-comparison-20261015.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# Blitz 理论数据与 278 万单局拆分','',
           '按本机原版录像核对过的计分规则计算。所有表格均为120秒，分数不含软降／硬降，除非明确写“原生成绩”。',
           '', '## 先看结论', '',
           '- 当前749块的速度，若始终完成4＋4＋6：64次PC；没有T-spin和消四的计分包络为2,787,800–3,121,050。',
           '- 同749块始终完成纯四行：74次PC，零T-spin／零消四包络3,161,900–3,432,700。',
           '- 允许高收益事件后，两种抽象上界分别4,995,300和5,330,000；均没有证明地形可达，不能当作本机或随机队列的承诺。',
           '- 278万这局实际57PC、17次T-spin、0消四，表明PC密度与PPS都还有空间；它不是一局始终不断的4＋4＋6或纯四行。',
           '', '## 不同速度的计分包络', '',
           '| PPS / 块数 | 理想446 PC | 446无T-spin／无消四 | 理想纯四行PC | 纯四行无T-spin／无消四 |',
           '|---|---:|---:|---:|---:|']
    for r in rows:
        a,b=r['446'],r['pure4']
        lines.append(f"| {r['pps']:.3f} / {r['pieces']} | {a['pcs']} | {a['plain_min']:,}–{a['plain_max']:,} | {b['pcs']} | {b['plain_min']:,}–{b['plain_max']:,} |")
    lines+=['', '范围来自普通Single/Double/Triple、combo及PC结算等级不同。每次消行先按当前等级算分，再升级。上下端是抽象事件模型的端点；下端也不是随机实机保底。749块的6.242 PPS使用实际749/120，而非把6.24乘120后截断。',
            '', '## 允许高收益事件的宽松上界', '', '| 块数 | 446 | 纯四行 |','|---:|---:|---:|']
    for r in rows:lines.append(f"| {r['pieces']} | {r['446']['relaxed_max']:,} | {r['pure4']['relaxed_max']:,} |")
    lines+=['', '上界允许完整T-spin（含零行）、消四、B2B与combo，并限制每个袋循环的T数量及每步格数。不约束具体四格块形状、七袋内顺序、SRS路径、锁定计时、有限预览和搜索成本。因此，不能把所有高分动作独立加满，也不能称此表为TETR.IO的绝对最高分。若Hold跨周期改变T库存，须重做全局库存模型。',
            '', '## 2,788,043 的实际组成', '', '| 项目 | 分数 | 占原生总分 |','|---|---:|---:|']
    labels=dict(pc='PC额外奖励',normal='普通消行基础分',spin='T-spin基础分（含零行）',b2b='B2B额外分',combo='Combo额外分',drop_and_nonclearing_tail='软／硬降分及不消行自然尾块')
    for key,value in actual['components'].items():lines.append(f"| {labels[key]} | {value:,} | {value/actual['native']['score']:.2%} |")
    lines+=['', '受控748块消行总分2,749,350，原生749块最终2,788,043，差38,693。原生与受控消行、PC、T-spin、等级相同，尾块未增加消行或旋转奖励；差值属于下降计分，含尾块下降。17次T-spin中9次零行，只有4次TSD、1次TSS、3次mini single；所以不能将“17 T-spin”都按TSD计分。',
            '', '## 升级门槛与速度', '', '每级所需消行为 ceil(2.1×当前等级)，下一等级累计门槛为此前各级之和。下表假设空场开始，无垃圾行；每块四格、每行十格，因此块数至少 ceil(2.5×累计消行)。',
            '', '| 到达等级 | 累计消行 | 最少块数 | 两分钟最低平均PPS |','|---:|---:|---:|---:|']
    for r in levels:lines.append(f"| {r['level']} | {r['lines']} | {r['minimum_pieces']} | {r['minimum_pps']:.4f} |")
    lines+=['', '这是进入等级的最低块数，不是该等级整局稳定能力；未消堆积会增加实际所需块数。749块最多299行，只够刚进入17；理论上不够18。',
            '', '## 300万需要什么', '',
            '保持当前结构的其他计分不变，离300万还差211,957分。同等级增加一个PC的额外奖励是3500×L：L16为56,000，四个为224,000；L17为59,500。这里只是局部敏感度，不能保证同样749块能白加四个PC，动作和升级时点也会改变。',
            '', '如果始终完成纯四行、720块／6 PPS，零T-spin／零消四模型的下端已为3,033,900；若始终446，达到790块／6.5833 PPS时，该下端为至少300万。这些都以循环成功为前提，不是程序当前稳定保证。',
            '', '## 纯四行是否一定最好', '',
            '同等级、同速度、只算PC奖励：纯四行7PC/70块，446为6PC/70块，前者PC密度高16.67%。只在这个简化比较下，纯四行用446约6/7的PPS即可持平PC分。现实还要同时比较升级、T-spin/B2B、断链、搜索时间和可执行性，不能据此断言纯四行总分一定更高；当前推荐的PC搜索允许其他高度和消行续打。',
            '', '真正要优化的是单位真实时间的等级加权收益。纯四行的理论PC密度更高；446可能更好做成，并在DPC中赚旋转收益。提高完成率若以更长搜索为代价，也可能反而减分。',
            '', '## 公式与复算', '',
            '每次锁定得分 = 当前等级 × [消行／T-spin基础分 ×（满足B2B时1.5，否则1）＋50×此前连续消行数（本次消行时）＋3500×是否PC] ＋实际下降分。零行不触发B2B乘数；普通不消行打断combo，但保持B2B。',
            '', '普通Single/Double/Triple/Quad为100/300/500/800；完整T-spin零行/单/双/三行为400/800/1200/1600，mini零行/单/双为100/200/400。PC的3500是额外奖励，不替代本次消行分，也不被B2B单独乘1.5。',
            '', '复算：`python scripts/analyze-blitz-theory.py`。模型：pc_lab/blitz_bounds.py；数据：output/blitz-theory-comparison-20261015.json；原生审计：output/blitz-throughput-run3-audit.json。在线控制器不使用这些离线记录的未来来块。']
    (ROOT/'docs/Blitz理论与278万拆分.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    def table_html(headers,body):
        return '<div style="overflow:auto"><table style="width:100%;text-align:left"><thead><tr>'+''.join(f'<th>{escape(x)}</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{escape(str(x))}</td>' for x in row)+'</tr>' for row in body)+'</tbody></table></div>'
    comparison=table_html(['PPS / 块','446 PC','446无旋转／消四','纯四行PC','纯四行无旋转／消四'],[
        [f"{r['pps']:.3f} / {r['pieces']}",r['446']['pcs'],f"{r['446']['plain_min']:,}–{r['446']['plain_max']:,}",r['pure4']['pcs'],f"{r['pure4']['plain_min']:,}–{r['pure4']['plain_max']:,}"] for r in rows])
    parts=table_html(['278万实际组成','分数','占比'],[[labels[k],f'{v:,}',f"{v/actual['native']['score']:.2%}"] for k,v in actual['components'].items()])
    upper=table_html(['块数','446宽松上界','纯四行宽松上界'],[[r['pieces'],f"{r['446']['relaxed_max']:,}",f"{r['pure4']['relaxed_max']:,}"] for r in rows])
    html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Blitz理论与278万拆分</title><link rel="stylesheet" href="/style.css"><main class="blitz-guide"><p><a href="/">实验室</a> · <a href="/blitz-manual">实测与推荐配置</a></p><h1>同样的速度，理论上能得多少分？</h1><section class="panel"><h2>749块：446约279–312万，纯四行约316–343万</h2><p>两分钟749块＝6.242 PPS。假设始终完成指定循环，446有64次PC，纯四行有74次；上面范围不含T-spin、消四和下降分。278万实测局只有57次PC。</p><p><strong>这是有条件的计分包络，未证明具体来块与操作可达。</strong>不能当作每局保证，也不能把理论差距全归因于运气。</p></section><section class="panel"><h2>不同速度：不含T-spin、消四与下降分</h2>'''+comparison+'''<p>循环始终成功；格数、PC边界、升级、combo均计算。尾段未完成PC也保留。范围来自消行拆分与结算等级不同。</p></section><section class="panel"><h2>278万这局的分数从哪里来</h2>'''+parts+'''<p>PC贡献79.46%；实际0消四、B2B额外分为0。17次T-spin有9次零行，不等于17个TSD。748个受控块的消行分为2,749,350，原生最终分2,788,043，差38,693属于下降计分及不消行尾块。</p></section><section class="panel"><h2>宽松上界不是可实现承诺</h2>'''+upper+'''<p>这列另外允许T-spin、消四、B2B，并限制T库存；尚未联合约束具体块形、袋内顺序、SRS、锁定时间、有限预览和搜索成本。都不含下降分，不是绝对最高分。</p></section><section class="panel"><h2>冲300万与更高等级</h2><p>纯四行如果能持续完成，720块／6 PPS的零T-spin、零消四包络下端为3,033,900。446在790块／6.5833 PPS才到这个300万条件下端。现实得先证明能持续，不能把假设变成程序保底。</p><p>进入Level17至少294行／735块／6.125 PPS；Level18至少330行／825块／6.875 PPS；Level19至少368行／920块／7.667 PPS。749块不足以进入18。</p><p>当前离300万差211,957分。保持其他计分不变，L16四个额外PC奖励为224,000分；实际增加PC会同时改变消行、升级和时间，不能直接视为白赚。</p><h2>怎么选择策略</h2><p>同等级、同速度、仅PC奖励，纯四行密度高16.67%。但446可能更容易完成并额外赚旋转收益；当前PC搜索也允许不同高度和断链续打。最终比较单位真实时间的等级加权得分。</p><p>详细公式、升级表、模型约束与原生拆分见项目 docs/Blitz理论与278万拆分.md。数据 output/blitz-theory-comparison-20261015.json，由 scripts/analyze-blitz-theory.py 复算。</p></section></main></html>'''
    (ROOT/'ui/blitz-bounds.html').write_text(html,encoding='utf-8')
    print(json.dumps(dict(actual=actual,rows=rows,levels=levels),ensure_ascii=False))


if __name__=='__main__':main()
