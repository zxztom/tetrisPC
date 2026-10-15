"""Import the author's public four-piece field data, preserving attribution.

Images are structured field data, sampled at cell centers. Reported
coverage is a source ranking, not this bot's measured success rate.
"""
import concurrent.futures
from collections import Counter
import io,json,re,time,urllib.request,colorsys,argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from PIL import Image
from pc_lab.engine import shape
from pc_lab.solver import ROOT

BASE='https://knewjade.github.io/best-chance-field/'
PALETTE={(0,153,153):'I',(0,0,153):'J',(153,102,0):'L',(153,153,0):'O',
         (0,204,0):'S',(153,0,153):'T',(153,0,0):'Z',(0,0,0):'_', (17,17,17):'_'}
HUES={piece:colorsys.rgb_to_hsv(*(v/255 for v in rgb))[0]
      for rgb,piece in PALETTE.items() if piece!='_'}


def color_piece(rgb):
    if max(rgb)<30:return '_'
    h,s,v=colorsys.rgb_to_hsv(*(v/255 for v in rgb))
    def distance(target):return min(abs(h-target),1-abs(h-target))
    piece=min(HUES,key=lambda p:distance(HUES[p]))
    if s<.5 or distance(HUES[piece])>.06:raise ValueError('Unknown field color '+str(rgb))
    return piece


def partitions(rows,signature):
    field={(x,3-y):p for y,row in enumerate(rows) for x,p in enumerate(row) if p!='_'}
    results=[]
    def visit(left,counts,ops):
        if not left:results.append(ops);return
        if len(results)>=16:return
        anchor=min(left,key=lambda p:(p[1],p[0]));piece=field[anchor]
        if not counts[piece]:return
        seen=set()
        for r in range(4):
            form=shape(piece,r)
            for dx,dy in form:
                ox,oy=anchor[0]-dx,anchor[1]-dy
                cells=frozenset((ox+x,oy+y) for x,y in form)
                if cells in seen:continue
                seen.add(cells)
                if cells<=left and all(field[p]==piece for p in cells):
                    counts[piece]-=1
                    visit(left-cells,counts,ops+[{'piece':piece,'original_cells':sorted(cells)}])
                    counts[piece]+=1
    visit(set(field),Counter(signature),[])
    return results


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--offline',action='store_true')
    args=parser.parse_args()
    raw=(ROOT/'tools/reference/best-chance.html').read_text(encoding='utf-8')
    entries=[]
    for phase,section in re.findall(r'<section id="count(\d+)">(.*?)</section>',raw,re.S):
        if int(phase)>7:continue
        for article in re.findall(r'<article>(.*?)</article>',section,re.S):
            match=re.search(r'id="m">([IJLOSTZ]+).*?src="\./(img/[^"]+).*?id="p">([\d.]+)',article)
            if match:entries.append((int(phase),*match.groups()))
    cache=ROOT/'tools/reference/best-chance-images';cache.mkdir(exist_ok=True)
    def fetch(entry):
        phase,signature,name,coverage=entry
        file=cache/Path(name).name
        for attempt in range(3):
            try:
                if file.is_file():blob=file.read_bytes()
                elif not args.offline:
                    blob=urllib.request.urlopen(BASE+name,timeout=12).read();file.write_bytes(blob)
                else:raise FileNotFoundError('Missing cached image '+str(file))
                img=Image.open(io.BytesIO(blob)).convert('RGB');w,h=img.size
                rows=[]
                for y in range(4):
                    row=''
                    for x in range(10):
                        rgb=img.getpixel((int((x+.5)*w/10),int((y+.5)*h/4)))
                        row+=color_piece(rgb)
                    rows.append(row)
                assert Counter(c for row in rows for c in row if c!='_')==Counter({p:n*4 for p,n in Counter(signature).items()})
                variants=partitions(rows,signature)
                # A completed setup row clears while the four pieces are
                # placed. The image describes their original coordinates,
                # not the final post-clear board.
                assert variants
                return {'phase':phase,'signature':signature,'rows':rows,'reported_coverage':float(coverage),
                        'operations':variants,'source_image':BASE+name,
                        'setup_cleared_lines':sum('_' not in row for row in rows)}
            except Exception as exc:
                if attempt==2:return {'error':str(exc),'entry':entry}
                time.sleep(.2)
    fields=[];errors=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        for i,result in enumerate(pool.map(fetch,entries),1):
            (errors if 'error' in result else fields).append(result)
            if i%100==0:print('Imported',i,'/',len(entries),flush=True)
    data={'source':BASE,'author':'knewjade','reported_coverage_is_bot_success_rate':False,
          'imported_date':'2026-10-15','fields':fields,'errors':errors}
    (ROOT/'data/best-chance-fields.json').write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(json.dumps({'fields':len(fields),'errors':len(errors),'examples':errors[:2]},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
