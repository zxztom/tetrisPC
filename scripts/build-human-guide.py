"""Build a no-seed human guide from verified desktop placements.

Historical Next values are reconstructed by source identity, never used
as a source of future information by the live bot.
"""
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from pc_lab.engine import cells,fits,lock,load_kicks,preferred_route,empty_board
from pc_lab.solver import ROOT

SOURCE=ROOT/'output/live-20261013-233735-53c38fb6/session.json'
NAMES={'left':'左一格','right':'右一格','cw':'顺时针90°','ccw':'逆时针90°',
       'soft_drop':'软降至接触面，松开','hard_drop':'硬降锁定','hold':'Hold'}


def replay(board,piece,actions,kicks):
    x,y,r=4,21,0
    frames=[{'cells':cells(piece,r,x,y),'label':'出生位置'}]
    for action in actions:
        if action in ('left','right'):x+=-1 if action=='left' else 1
        elif action in ('cw','ccw'):
            nr=(r+(1 if action=='cw' else -1))%4
            for dx,dy in kicks[piece+'.'+'NESW'[r]+'NESW'[nr]]:
                if fits(board,cells(piece,nr,x+dx,y+dy)):
                    x,y,r=x+dx,y+dy,nr;break
            else:raise AssertionError('Impossible rotation')
        elif action in ('soft_drop','hard_drop'):
            while fits(board,cells(piece,r,x,y-1)):y-=1
        else:raise AssertionError(action)
        points=cells(piece,r,x,y)
        assert fits(board,points)
        frames.append({'cells':points,'label':NAMES[action]})
    return frames


INTRO='''# 不知道种子，怎样完成连续 PC

这份说明针对 TETR.IO 单人、无垃圾、七袋、无重力练习。目标是 **4 行 PC → 4 行 PC → 6 行 DPC**。你只需要读取棋盘、当前块、Hold 和 Next；不需要取得或填写种子。每次出现新块后，更新判断。

本说明包含通用决策方法，以及一轮实际随机 ZEN 的 35 块图解。图解适用于其中那组块序和棋盘；任意新开的随机局，需要根据自己的 Next 选分支，不能照抄整轮按键。当前方法与程序都不保证无限不断链。

## 1. 先确认游戏规则

TETR.IO 的 ZEN 与可自定义的 CUSTOM 不能混用规则。当前客户端的 ZEN 五个 Next 和 I 块 SRS+ 踢墙行为已经由本机截图、实际按键核对。CUSTOM 请确认七袋、零重力，并让 kick table 与求解规则一致；本程序实时默认 SRS+ 90°；CUSTOM 使用标准 SRS 时需在界面明确选择，ZEN 固定 SRS+。有重力模式尚未验证。

| 规则 | 对操作的影响 |
|---|---|
| 七袋 | 每袋 I/J/L/O/S/T/Z 各一块；袋内排列未知。 |
| 单格 Hold | 每次锁定之间只能使用一次；空 Hold 会拿走当前块并取 Next 第一块，有块时则交换。灰色 Hold 说明本块已经用过。 |
| 空中旋转 | 没有碰撞时按旋转中心转动；I 的顺、逆时针竖直朝向具有不同横向位置。朝向相似不等于落点相同。 |
| SRS+ 踢墙 | 碰撞后按规定次序试偏移，采用第一个合法结果。I 的部分尝试次序与标准 SRS 不同。 |
| 硬降 | 立即落下并锁定；按之前核对阴影或图解落点。 |
| 软降 | 落下但不会因这个动作立即硬锁；SDF 为 ∞ 时可瞬降至接触面，之后仍可旋入。 |
| 锁定延迟 | 触地后还有时间限制及重置规则，具体随模式设置。插入动作要连贯，不能假定可无限等待。 |
| DAS / ARR / DCD | 长按横移会连发，旋转和出生又可能影响连发时机。本说明的“左一格”指点按一次后松开。 |
| 180° | TETR.IO 提供独立按键，但当前程序和这轮图解只用 90°；一次 180°不能直接当成两次 90°的踢墙路线。 |

Handling、SDF 和旋入行为参见 [TETR.IO 官方 FAQ](https://tetrio.github.io/faq/mechanics.html)。I 块差异有 [官方问题仓库中的讨论与表格](https://github.com/tetrio/issues/issues/506)；该资料较早，关键 I 块案例又经过当前本机实测，不能把历史讨论当成所有当前模式的完整规则规范。可配置的 kick table、Next、lock delay 和 lock resets 可对照 [客户端配置参考](https://github.com/lemoncove/tetrio-bot-docs/blob/master/Room_Config.md)。

## 2. 为什么是 7+3、4+6、1+7+7

十列棋盘每行十格，每块四格。因此从空棋盘做四行 PC 要锁定 10 块，六行 PC 要锁定 15 块。三个阶段用掉 10+10+15=35 块，正好五袋；共消除 14 行。

| 阶段 | 累计锁定数 | 来源的理想分组 | 全清后检查 |
|---|---:|---|---|
| 第一 PC | 10 | 第一袋 7 + 第二袋 3 | 棋盘为空，记下剩余第二袋成员与 Hold。 |
| 第二 PC | 20 | 第二袋剩余 4 + 第三袋 6 | 三袋 21 块中还剩一块未锁定，用于 DPC。 |
| DPC | 35 | 那个额外块 1 + 第四袋 7 + 第五袋 7 | 棋盘再次为空，五袋来源各用一次。 |

这是**来源数量**的解释。Hold 能让不同袋的块交换锁定先后；第二次 PC 后额外块也未必在 Hold，可能在当前块。已经露出下一袋的块不等于用掉了它。图解这轮第 35 块将第六袋的 S 存入 Hold，换出第五袋的 T 完成 PC；这个 S 尚未锁定，属于下一轮。

## 3. 只看 Next，如何决定下一步

**先建立一张袋成员清单。** 新局第一块是第一袋起点。按来块来源记数，出生或空 Hold 取新块会推进队列，交换非空 Hold 不改变两个块的来源。不要把锁定数直接当作来源序号。

已知袋起点时，看到同袋六个不同成员，可以唯一推断第七个。例如第一块 T，Next 为 J I Z O S，则这一袋最后一个必是 L。仅看到任意六个不同字母、却不知道袋边界，不能这样推断。ZEN 中途清空棋盘也不会自动让随机队列回到袋边界；若起点不明，先记录后续，不能直接套新局第一袋推断。[七袋参考实现](https://github.com/lemoncove/tetrio-bot-docs/blob/master/Piece_RNG.md)

**每块都重复以下步骤：**

1. 记下当前块、Hold 是否可用、Next、棋盘，以及本阶段还要消几行。
2. 列出“用当前块”和“本块用一次 Hold”两类选择；Hold 不可用时只考虑当前块。
3. 给选中的块找落点。优先选择空中转好、横移后能直接落到的位置；阴影碰到别的块就检查是否有合法插入路径。
4. 看剩余空格能否由即将用到的块填满。**剩余块数 =（本阶段剩余行数 × 10 − 棋盘现有格数）÷ 4。** 每消行后再算；不能只看最高堆积高度。
5. 若收尾所需的块都已知，先确认完整收尾顺序，再执行。若还有未知块，保留多个可能收尾，优先选择它们共同可用的第一步；只执行这一块，等新 Next 出现后再判断。
6. 硬降后核对棋盘与 Hold。到第 10、20、35 块时检查全空及累计 4、8、14 行；中途提前 PC 就没有保持本轮规定节奏。

人类主要用已记住的结构与收尾形状完成第 3–5 步。程序则在未知处抽取有限个符合七袋的候选排列，搜索各自收尾，再比较首步；它默认最多抽取 8 个候选，不是穷举，也不是预知实际随机数。候选中有解不能证明真实未来一定有解。

**具体收尾例子：** 做到第一段第 7 块时，若共已消 1 行、棋盘还剩 18 格，剩余消行数为 3，则要再锁定 (30−18)÷4=3 块。当前块加 Next 已足以看到这三块；再考虑 Hold，按能填满并合法落入的顺序完成，而无需知道后面整袋的排列。实际是否有解仍取决于地形与这几个块。后面的图解提供真实地形示例。

## 4. 三段分别怎样做

**第一段：标准 PCO 为优先选择。** J/L/O 组成左侧矩形，S/Z/T 在另一侧搭形，尽可能保留 I。下面是程序使用的一种方向，`·` 表示空格，上面一行是第 4 行；镜像时 J↔L、S↔Z。它是目标结构，不是固定来块顺序。

```text
LLL·····SS
LOO····SST
JOO···ZZTT
JJJ····ZZT
1234567890
```

空格区域留给 Hold 与后续来块。根据当前袋顺序选左右镜像，先放支撑块，Hold 暂时无支撑的块；无法合法搭成时改用另一个 PC 地形，不能硬套此图。PCO 本身不是任意块序必成功，资料的理论比例也不是本程序成功率。[PCO 结构与收尾](https://harddrop.com/wiki/Perfect_Clear_Opener)

**第二段：继承剩余块。** 第一 PC 后记录 Hold、第二袋尚未锁定的四个来源和第三袋已露出的块。用这十个来源构建另一个四行解。优先在仍能完成 PC 的前提下，给下一段留下适合的额外块；不能为了指定余块牺牲这次全清。[Second Perfect Clear](https://harddrop.com/wiki/Second_Perfect_Clear)

**第三段：按额外块选 DPC 家族。** 核对前三袋唯一未锁定的块，再结合第四袋顺序选择正形或镜像。程序收录 O、S/Z、I、J/L、T 的结构；资料通常优先保留 O 或 S/Z，I 也可用。先搭结构，再看第五袋收尾。DPC 六行可以分次消掉，不要求最后一次按键同时消六行，也不把 T-Spin 当作全清成立的必要条件。[DPC 结构](https://harddrop.com/wiki/DPC_Setups)

DPC 页面写的 100% 带有可能需要 180°的条件；这里的 90°程序和有限 Next 决策不具备这个保证。若当前规则和块序下找不到收尾，暂停并检查其他分支；已经锁死的堆积不能靠改变按键速度修复。

## 5. 旋转与按键怎么执行

普通落点按 **必要的 Hold → 空中旋转 → 横移 → 检查阴影 → 硬降**。旋转和横移的先后以实际路线为准；靠墙转动可能触发踢墙，不能任意交换动作。

遇到插入，则按图解给出的 **旋转/横移 → 软降至支撑面并松开 → 再旋转或横移 → 核对 → 硬降**。软降不能提前换成硬降，后者会锁死方块。图解的第 3、7、15、31 块属于这种情况；第 15 块 S 要两次顺时针，中间在支撑面停住。

你报告的 I 在 Z 上方跑偏，来自落地后顺时针的 SRS+ 踢墙与旧预测不同。那一落点有更直接的路线：出生处 **逆时针一次 → 左点按四次 → 硬降**，I 的四格落在最左列。这个路线已在当前 ZEN 实机核对；它只适用于同一目标空隙，不是所有 I 块的统一操作。

图解使用逻辑动作名，按你的绑定执行。本项目当前绑定：←/→ 横移，↑ 顺时针，Ctrl 逆时针，Shift Hold，↓ 软降，空格硬降。左右每次点按后松开，避免 DAS 连发多走一格。连续两次同一旋转也要先松开。

自动操作间隔可设 0–2000 毫秒，默认 75；这是上一次松键到下一次按键的**最短间隔**，截图核对会让实际间隔更长。45 和 120 毫秒都完成过本机放置验证；大间隔可能使触地插入赶不上锁定时间。人工按键不用照着毫秒数，只需在硬降前核对落点。

## 6. 怎么使用这轮逐块图解

在网页的“无种子操作说明”中，用“上一块/下一块”查看 35 块。每步显示操作前当前块、Hold、五个 Next，以及目标落地、消行后棋盘；“动作演示”可查看出生到锁定的中间位置。棋盘列数从左到右为 1–10，行数从底部向上计；白框是本步方块。

这一轮来自实际 ZEN 随机窗口记录，机器人当时没有读取种子，三次 PC 及落点已实际核对。说明里的优先空中路线是在这些落点上**重新计算并离线逐动作验证**的；没有重新在实机执行整轮修改后的 35 块按键。另有当前实机 I 左列验证。原记录在第 62 块尝试时因 I 旋转差异停止，第一轮的成功不能推出后续无限成功。

想学同样操作，可逐步对照图解练习；自己的随机局只在当前块、Hold、棋盘及已知 Next 都相符时采用该分支。显示的下一步来自历史观测，只用来解释案例，不能把后面页面的块当作你当前游戏的未来来块。

## 7. 不会自己找收尾时，手动使用本机求解界面

你仍然自己在游戏中操作。打开实验室，选择当前阶段的**剩余消行数**，抄下当前棋盘，填入“当前块 + 可见 Next”，单独设置 Hold，并选与游戏一致的 SRS+ 或 SRS。允许旋入时选择“含软降和旋入”。点击求解，按回放路线逐块操作，每块落地后核对。

例如图解第 15 块之后：第二 PC 还剩三行，当前 I，Hold S，Next T O Z J O。选择“剩余三行收尾”，块序填 `ITOZJO`，Hold 选 S，棋盘从上到下填：

```text
__________
_T_______J
_TOOL_SSJJ
```

这三个输入行表示当前底部三行；顶行可以为空。选择 SRS+，求解会给出五块收尾。用到的当前块、Next 和 Hold 都已在画面上看见，不需要种子或整袋未来。它可能找到与历史图解不同的合法落点；采用一种经过验证的完整收尾即可，不要把两种方案的中间步骤混搭。

如果提示需要更多已知块，说明还不够看到完整收尾；不要编造隐藏 Next。先按结构方法放一块，再更新画面。若没有解，换可行地形分支；搜索未完成与已证明当前候选无解也要区分。

资料核查日期：2026-10-14。实现包含 SRS+ 的 90°表；尚未声称覆盖 180°、所有自定义规则或有重力模式。
'''


def render_md(text):
    """Small renderer for this fixed generated document, no remote assets."""
    out=[];in_code=False;in_table=False
    def inline(s):
        s=html.escape(s)
        s=re.sub(r'\[([^\]]+)\]\((https://[^)]+)\)',r'<a href="\2" target="_blank" rel="noreferrer">\1</a>',s)
        s=re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',s)
        return s
    for line in text.splitlines():
        if line.startswith('```'):
            if in_table:out.append('</table>');in_table=False
            out.append('</code></pre>' if in_code else '<pre><code>');in_code=not in_code;continue
        if in_code:out.append(html.escape(line));continue
        if line.startswith('|'):
            if not in_table:out.append('<table>');in_table=True
            if re.match(r'^\|[-:| ]+\|$',line):continue
            out.append('<tr>'+''.join('<td>'+inline(c.strip())+'</td>' for c in line.strip('|').split('|'))+'</tr>');continue
        if in_table:out.append('</table>');in_table=False
        if not line.strip():continue
        if line.startswith('# '):out.append('<h1>'+inline(line[2:])+'</h1>')
        elif line.startswith('## '):out.append('<h2>'+inline(line[3:])+'</h2>')
        else:out.append('<p>'+inline(line)+'</p>')
    if in_table:out.append('</table>')
    return '\n'.join(out)


def main():
    record=json.loads(SOURCE.read_text(encoding='utf-8'))
    known={}
    for step in record['steps']:
        known[step['source_index']]=step['piece']
        i=step['global_queue_index_after']
        known[i]=step['observed_active_after']
        known.update({i+n+1:p for n,p in enumerate(step['observed_next_after'])})
    kicks=load_kicks(ROOT/'data/srsplus90.properties');steps=[]
    for number,original in enumerate(record['steps'][:35],1):
        step=dict(original);board=tuple(step['board_before']);i=step['global_queue_index_before']
        route=preferred_route(board,step['piece'],step['cells'],kicks)
        frames=replay(board,step['piece'],route['actions'],kicks)
        assert set(map(tuple,frames[-1]['cells']))==set(map(tuple,step['cells']))
        after,placed,cleared=lock(board,frames[-1]['cells'],step['piece'])
        assert after==tuple(step['board_after']) and cleared==tuple(step['cleared_rows'])
        step.update(route,number=number,current_before=known[i],next_before=''.join(known[n] for n in range(i+1,i+6)),
                    frames=frames,actions_text=' → '.join(([NAMES['hold']] if step['hold_used'] else [])+[NAMES[a] for a in route['actions']]),
                    target_columns=sorted({x+1 for x,y in step['cells']}),pc=after==empty_board())
        steps.append(step)
    pcs=[s['number'] for s in steps if s['pc']]
    assert pcs==[10,20,35]
    assert sorted(s['source_index'] for s in steps)==list(range(35))
    assert sum(len(s['cleared_rows']) for s in steps)==14
    data={'source_recording':str(SOURCE.relative_to(ROOT)), 'uses_seed':False,'rules':'SRS+90',
          'native_placements_verified':True,'revised_routes_verified_offline':True,
          'revised_full_cycle_retested_native':False,'pc_indices':pcs,'steps':steps}
    out=ROOT/'docs';out.mkdir(exist_ok=True)
    (out/'human-replay.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    appendix=['\n## 附录：35 块操作表\n','每一步开始于该块出生位置；“当前”是使用 Hold 前的块，Next 从近到远。','\n| 步 | 段 | 当前 | Hold 前→后 | Next 五块 | 放置块 | 操作 | 消行 |\n|---|---|---|---|---|---|---|---|']
    for s in steps:
        appendix.append(f"| {s['number']} | {s['stage']} | {s['current_before']} | {s['hold_before'] or '空'}→{s['hold_after'] or '空'} | {s['next_before']} | {s['piece']} | {s['actions_text']} | {len(s['cleared_rows'])}{' / PC' if s['pc'] else ''} |")
    appendix.append('\n## 附录：逐步落地棋盘\n\n每图显示硬降锁定、消行之前；上为第 8 行，下为第 1 行。具体消行之后的状态见网页。')
    for s in steps:
        appendix.append(f"\n### 第 {s['number']} 块 {s['piece']}\n\n{s['actions_text']}\n\n```text\n"+'\n'.join(row.replace('_','·') for row in reversed(s['board_placed'][:8]))+'\n1234567890\n```')
    (out/'不知道种子的连续PC说明.md').write_text(INTRO+'\n'.join(appendix),encoding='utf-8')
    template=(ROOT/'ui/manual-template.html').read_text(encoding='utf-8')
    document=template.replace('<!--GUIDE-->',render_md(INTRO)).replace('/*REPLAY_DATA*/',json.dumps(data,ensure_ascii=False).replace('</','<\\/'))
    (ROOT/'ui/manual.html').write_text(document,encoding='utf-8')
    (out/'不知道种子的连续PC图解.html').write_text(document,encoding='utf-8')
    print(json.dumps({'steps':35,'pc_indices':pcs,'tuck_steps':[s['number'] for s in steps if 'soft_drop' in s['actions']],
                      'new_actions_replayed':sum(len(s['actions']) for s in steps),'seed_read':False},ensure_ascii=False))


if __name__=='__main__':main()
