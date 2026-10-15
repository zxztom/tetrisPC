"""Draw original SVG explanations, using only the project's own replay example."""
import json
from html import escape
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
ASSETS=ROOT/'docs/assets'
COLORS=dict(I='#0284c7',O='#eab308',T='#9333ea',S='#16a34a',Z='#dc2626',J='#2563eb',L='#ea580c')


def text(x,y,value,size=20,weight=400,color='#183044'):
    return f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{color}">{escape(str(value))}</text>'


def rect(x,y,w,h,color,stroke='none',radius=0):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{color}" stroke="{stroke}"/>'


def save(name,w,h,content,title):
    (ASSETS/name).write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{escape(title)}"><title>{escape(title)}</title><g font-family="Microsoft YaHei, Noto Sans CJK SC, sans-serif">'+rect(0,0,w,h,'#f6fafc')+content+'</g></svg>',encoding='utf-8')


def seven_bag():
    shapes=dict(I=[(0,0),(1,0),(2,0),(3,0)],O=[(0,0),(1,0),(0,1),(1,1)],
                T=[(1,0),(0,1),(1,1),(2,1)],S=[(1,0),(2,0),(0,1),(1,1)],
                Z=[(0,0),(1,0),(1,1),(2,1)],J=[(0,0),(0,1),(1,1),(2,1)],
                L=[(2,0),(0,1),(1,1),(2,1)])
    out=text(30,38,'七种块：每一种都由四格组成',26,700)
    for i,(piece,points) in enumerate(shapes.items()):
        x=35+i*135
        for dx,dy in points:out+=rect(x+dx*24,70+dy*24,23,23,COLORS[piece],radius=2)
        out+=text(x+20,148,piece,22,700)
    out+=text(30,197,'七袋：每袋七种各一个，只打乱顺序',23,700)
    for row,sequence in enumerate(('ITOLSJZ','SJIZTOL')):
        y=225+row*64;out+=text(32,y+27,f'第{row+1}袋',18)
        for i,piece in enumerate(sequence):
            out+=rect(140+i*94,y,76,42,COLORS[piece],radius=6)+text(168+i*94,y+29,piece,23,700,'white')
        out+=text(820,y+27,'→ 下一袋',19)
    save('pc-seven-bag.svg',1000,365,out,'七种四格方块，以及两袋随机顺序的例子')


def loops():
    out=text(30,40,'两种方法都在做：空场 → 拼图与消行 → 再次空场',25,700)
    out+=text(30,91,'446：三次PC',24,700)
    for i,(label,pieces) in enumerate((('4行PC',10),('4行PC',10),('6行PC',15))):
        x=35+i*320
        out+=rect(x,111,280,83,'#d9f1ed' if i<2 else '#fff0ce',radius=10)
        out+=text(x+25,145,label,25,700)+text(x+25,177,f'{pieces}块 → 棋盘清空',18)
        if i<2:out+=text(x+289,164,'→',24,700)
    out+=text(35,230,'累计：10 → 20 → 35块；35 = 5 × 7，回到七袋相位',21,700)
    out+=text(30,292,'4444444：七次四行PC',24,700)
    for i in range(7):
        x=35+i*136
        out+=rect(x,312,115,74,'#e3eafd',radius=8)
        out+=text(x+19,343,'4行PC',19,700)+text(x+27,370,'10块',17)
        if i<6:out+=text(x+117,355,'→',19,700)
    out+=text(35,423,'累计：10 → 20 → 30 → 40 → 50 → 60 → 70块',21,700)
    out+=text(35,458,'70 = 10 × 7。六次只有60块；第七次才完成这一轮对齐。',20)
    out+=text(35,504,'数字是每段累计消行数；每次PC后都空场，下一轮块序仍然随机。',18)
    save('pc-loop-comparison.svg',1000,530,out,'446在35块后对齐；七次四行PC在70块后对齐')


def actual_example():
    r=json.loads((ROOT/'docs/pure4-human-replay.json').read_text(encoding='utf-8'));steps=r['steps']
    assert r['native_placements_verified']
    assert ''.join(x['piece'] for x in steps[:10])=='ITZSLJTOIO'
    assert sum(len(x['cleared_rows']) for x in steps[:7])==1
    assert sum(len(x['cleared_rows']) for x in steps[:9])==2
    assert len(steps[9]['cleared_rows'])==2
    assert all(x=='__________' for x in steps[9]['board_after'])
    panels=[('① 放下前4块',steps[3]['board_after'],'16格，尚未消行'),
            ('② 第7块后',steps[6]['board_after'],'累计消1行，还剩18格'),
            ('③ 第10块O刚落下',steps[9]['board_placed'],'此前已消2行；再消满的2行'),
            ('④ 消行结束：PC',steps[9]['board_after'],'10块共40格，累计消4行')]
    out=text(26,40,'真实例子：十块四行PC，中途可以先消行',25,700)
    for i,(title,board,caption) in enumerate(panels):
        x=35+(i%2)*485;y=79+(i//2)*265
        out+=text(x,y,title,23,700)
        for row in range(5):
            for col in range(10):
                piece=board[row][col];cx=x+col*31;cy=y+24+(4-row)*31
                out+=rect(cx,cy,30,30,COLORS.get(piece,'#e6edf2'),'#bbcbd7',2)
        if i==2:
            for col,row in steps[9]['cells']:
                out+=f'<rect x="{x+col*31+2}" y="{y+24+(4-row)*31+2}" width="26" height="26" fill="none" stroke="#422500" stroke-width="3"/>'
        out+=text(x,y+205,caption,18)
    out+=text(35,603,'颜色表示块种类；深框标出最后的O。图只显示底部五行。',18)
    out+=text(35,635,'锁定顺序 I T Z S L J T O I O；这是具体案例，不是任意来块都能照抄。',18)
    save('pc-ten-piece-example.svg',1000,662,out,'本项目真实十块PC的四个棋盘阶段')


def main():
    ASSETS.mkdir(parents=True,exist_ok=True)
    seven_bag();loops();actual_example()
    assert 35*4==14*10 and 70*4==28*10 and 60%7!=0 and 70%7==0
    print('Wrote 3 SVG figures; replay and cycle arithmetic checked.')


if __name__=='__main__':main()
