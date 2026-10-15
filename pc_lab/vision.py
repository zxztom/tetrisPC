"""Pixel-only board/Hold/Next recognition, calibrated to the current skin."""
from collections import deque
import colorsys
from dataclasses import dataclass, asdict
from pathlib import Path
import numpy as np

from .engine import BASE, cells,poses_for


def runs(mask):
    start = None
    for index, value in enumerate(list(mask) + [False]):
        if value and start is None:
            start = index
        elif not value and start is not None:
            yield start, index
            start = None


def grouped(indices, gap=6):
    result = []
    for value in indices:
        if not result or value - result[-1][-1] > gap:
            result.append([value])
        else:
            result[-1].append(value)
    return [round(sum(group) / len(group)) for group in result]


@dataclass
class Geometry:
    left: float
    top: float
    cell: float
    width: int
    height: int

    @property
    def right(self):
        return self.left + 10 * self.cell

    @property
    def bottom(self):
        return self.top + 20 * self.cell

    def to_dict(self):
        return asdict(self)


def detect_geometry(image):
    a = np.asarray(image).astype(np.int16)
    h, width = a.shape[:2]
    white = (a.min(2) > 180) & ((a.max(2) - a.min(2)) < 45)
    counts = white.sum(0)
    indices = [x for x in range(int(width*.2), int(width*.85)) if counts[x] > h*.45]
    columns = grouped(indices)
    possibilities = []
    for left in columns:
        for right in columns:
            size = right - left
            if not width*.12 < size < width*.3:
                continue
            shared = white[:, left] & white[:, right]
            segments = list(runs(shared))
            if not segments:
                continue
            top, bottom = max(segments, key=lambda pair: pair[1]-pair[0])
            length = bottom - top
            error = abs(length / size - 2)
            if error < .12 and length > h*.45:
                possibilities.append((error, left, right, top, bottom))
    if not possibilities:
        # ZEN's orange progress meter can cover the right white border.
        # Its left border still spans the full twenty rows; retain a bottom
        # anchor so the filled cells stay aligned while that meter rises.
        candidates=[]
        for left in columns:
            if not width*.35<left<width*.55:continue
            segments=list(runs(white[:,left]))
            if not segments:continue
            top,bottom=max(segments,key=lambda pair:pair[1]-pair[0])
            size=(bottom-top-6)/20
            if bottom-top>h*.45 and width*.12<size*10<width*.3:
                candidates.append((left,bottom,size))
        if candidates:
            left,bottom,size=min(candidates)
            return Geometry(left+3,bottom-3-20*size,size,width,h)
        raise ValueError("未识别到十列二十行棋盘，请进入练习并保持窗口完整可见。")
    _, left, right, top, bottom = min(possibilities)
    # Border center → inner grid. Using the actual edge span minimizes drift.
    size = (right-left-6)/10
    return Geometry(left+3, bottom-3-20*size, size, width, h)


def colorful(rgb):
    maximum = rgb.max(axis=2).astype(float)
    minimum = rgb.min(axis=2).astype(float)
    return (maximum > 85) & ((maximum-minimum) / np.maximum(maximum, 1) > .45)


def component_boxes(mask, min_area=10):
    """Four-connected components, joining row spans instead of pixels."""
    mask=np.asarray(mask,dtype=bool)
    padded=np.pad(mask,((0,0),(1,1)))
    edges=padded[:,1:]!=padded[:,:-1]
    # Locate all transitions in one array operation. Preview panels contain
    # many blank rows; repeatedly calling flatnonzero for every color and
    # every row dominated recognition time on the native high-DPI window.
    rows,columns=np.nonzero(edges)
    if not len(rows):return []
    row_starts=np.r_[0,np.flatnonzero(rows[1:]!=rows[:-1])+1,len(rows)]
    parents=[];spans=[];previous=[]
    def root(index):
        while parents[index]!=index:
            parents[index]=parents[parents[index]];index=parents[index]
        return index
    previous_y=-2
    for begin,end in zip(row_starts[:-1],row_starts[1:]):
        y=int(rows[begin]);ends=columns[begin:end];current=[];offset=0
        if previous_y!=y-1:previous=[]
        previous_y=y
        for left,right in zip(ends[::2],ends[1::2]):
            left=int(left);right=int(right);index=len(parents)
            parents.append(index);spans.append((left,y,right,y+1,right-left))
            while offset<len(previous) and previous[offset][1]<=left:offset+=1
            for pl,pr,pi in previous[offset:]:
                if pl>=right:break
                parents[root(pi)]=root(index)
            current.append((left,right,index))
        previous=current
    boxes={}
    for index,span in enumerate(spans):
        key=root(index);left,top,right,bottom,area=span
        if key in boxes:
            a,b,c,d,n=boxes[key];span=(min(a,left),min(b,top),max(c,right),max(d,bottom),n+area)
        boxes[key]=span
    return sorted((b for b in boxes.values() if b[4]>=min_area),key=lambda b:(b[1],b[0]))


def read_previews(image, geom, array=None):
    a = np.asarray(image) if array is None else array
    # Downsample only the preview panel, leaving plenty of pixels per mino.
    left=int(geom.right + geom.cell*.8);right=int(geom.right + geom.cell*5.8)
    top=int(geom.top + geom.cell*.9);bottom=int(geom.bottom)
    region=a[max(0,top):bottom,left:right]
    scale=3
    small=region[::scale,::scale]
    mask=colorful(small)
    # The client's blue mouse glow can connect two adjacent I previews.
    # Group by sprite hue before finding components so the glow cannot
    # merge them or shift the remaining queue upward.
    rgb=small.astype(float);hi=rgb.max(2);lo=rgb.min(2);delta=hi-lo
    hue=np.zeros_like(hi);safe=np.maximum(delta,1)
    red=(hi==rgb[:,:,0]);green=(hi==rgb[:,:,1])&~red;blue=~red&~green
    hue[red]=((rgb[:,:,1]-rgb[:,:,2])/safe)[red]%6
    hue[green]=((rgb[:,:,2]-rgb[:,:,0])/safe+2)[green]
    hue[blue]=((rgb[:,:,0]-rgb[:,:,1])/safe+4)[blue]
    hue/=6
    # Skin borders can leave a thin dark seam between adjacent minos. Close
    # those seams for component grouping, but sample the original colors.
    boxes=[]
    for color in DEFAULT_HUES.values():
        distance=np.abs(hue-color);distance=np.minimum(distance,1-distance)
        group=mask&(distance<.048)
        if not group.any():continue
        padded=np.pad(group,1);joined=np.zeros_like(group)
        for dy in range(3):
            for dx in range(3):joined|=padded[dy:dy+group.shape[0],dx:dx+group.shape[1]]
        boxes.extend(component_boxes(joined,min_area=40))
    boxes=list({box[:4]:box for box in boxes}.values())
    sprites=[]
    for x1,y1,x2,y2,area in sorted(boxes,key=lambda b:b[1]):
        bw,bh=x2-x1,y2-y1
        if min(bw,bh)<3 or area<40:
            continue
        ratio=bw/bh
        cols,rows=(4,1) if ratio>3 else (2,2) if .8<ratio<1.2 else (3,2)
        # The one-pixel dilation adds two pixels to each bounding axis.
        # At half resolution that is a significant fraction of one mino,
        # especially for the I sprite's single row.
        unit=(bw-2)/cols
        if not .7*geom.cell/scale < unit < 1.35*geom.cell/scale:
            continue
        if abs((bh-2)/rows-unit)>unit*.25:
            continue
        pattern=[]; samples=[]
        for row in range(rows):
            for col in range(cols):
                x=round(x1+(col+.5)*bw/cols);y=round(y1+(row+.5)*bh/rows)
                if y<small.shape[0] and x<small.shape[1] and mask[y,x]:
                    pattern.append((col,rows-1-row));samples.append(small[y,x])
        if len(pattern)!=4:
            continue
        shape_set=set(pattern)
        piece=None
        for name,points in BASE.items():
            minx=min(x for x,y in points);miny=min(y for x,y in points)
            if {(x-minx,y-miny) for x,y in points}==shape_set:
                piece=name;break
        if piece:
            rgb=np.median(samples,axis=0)/255
            sprite_hue=colorsys.rgb_to_hsv(*rgb)[0]
            distance=abs(sprite_hue-DEFAULT_HUES[piece])
            if min(distance,1-distance)>.09:continue
            sprites.append({"piece":piece,"hue":sprite_hue,
                            "box":[left+x1*scale,top+y1*scale,left+x2*scale,top+y2*scale]})
    # Yellow/orange bevels can be selected by two adjacent hue masks.
    # Dedupe the same physical sprite by overlap, rather than exact bounds;
    # neighboring equal pieces have separate boxes and must remain separate.
    unique=[]
    for sprite in sorted(sprites,key=lambda p:-(p['box'][2]-p['box'][0])*(p['box'][3]-p['box'][1])):
        x1,y1,x2,y2=sprite['box'];area=(x2-x1)*(y2-y1)
        overlap=False
        for other in unique:
            a,b,c,d=other['box'];intersection=max(0,min(x2,c)-max(x1,a))*max(0,min(y2,d)-max(y1,b))
            if intersection/(area+(c-a)*(d-b)-intersection)>.7:overlap=True;break
        if not overlap:unique.append(sprite)
    sprites=sorted(unique,key=lambda p:p['box'][1])
    if len(sprites)<3:
        raise ValueError("Next 队列识别不完整，等待动画稳定或检查皮肤。")
    return sprites


DEFAULT_HUES={"Z":.99,"L":.075,"O":.145,"S":.23,"I":.46,"J":.68,"T":.84}


def aligned_board(image,geom):
    """ZEN level-up tilts the whole board, including the preview panels."""
    a=np.asarray(image)
    top=max(0,round(geom.top+geom.cell));bottom=min(image.height,round(geom.bottom-geom.cell))
    # The cached inner edge is immediately to the right of the white border.
    left=max(0,round(geom.left-4));right=min(image.width,round(geom.left+1))
    part=a[top:bottom,left:right]
    if part.size==0:return False
    white=(part.min(2)>180)&((part.max(2).astype(int)-part.min(2))<45)
    return white.any(1).mean()>.45


def gray_hold_piece(region,cell):
    small=region[::2,::2]
    maximum=small.max(2);minimum=small.min(2)
    mask=(maximum>28)&(maximum<95)&(maximum-minimum<15)
    padded=np.pad(mask,1);joined=np.zeros_like(mask)
    for dy in range(3):
        for dx in range(3):joined|=padded[dy:dy+mask.shape[0],dx:dx+mask.shape[1]]
    for x1,y1,x2,y2,area in component_boxes(joined,40):
        bw,bh=x2-x1,y2-y1;ratio=bw/bh
        cols,rows=(4,1) if ratio>3 else (2,2) if .8<ratio<1.2 else (3,2)
        unit=bw/cols
        if not .65*cell/2<unit<1.4*cell/2 or abs(bh/rows-unit)>unit*.3:continue
        points=set()
        for row in range(rows):
            for col in range(cols):
                x=round(x1+(col+.5)*bw/cols);y=round(y1+(row+.5)*bh/rows)
                if y<mask.shape[0] and x<mask.shape[1] and mask[max(0,y-2):y+3,max(0,x-2):x+3].mean()>.4:
                    points.add((col,rows-1-row))
        if len(points)!=4:continue
        for name,base in BASE.items():
            minx=min(x for x,y in base);miny=min(y for x,y in base)
            if {(x-minx,y-miny) for x,y in base}==points:return name
    return None


def is_zen(image):
    path=Path(__file__).resolve().parent.parent/'data/zen-header.png'
    if not path.is_file():return False
    from PIL import Image
    template=np.asarray(Image.open(path).convert('RGB'))
    normalized=image.resize((1527,round(image.height*1527/image.width)))
    expected=template.min(2)>160
    if expected.sum()<100:return False
    for left in (1415,1030):
        actual=np.asarray(normalized.crop((left,25,left+102,85))).min(2)>160
        padded=np.pad(actual,1);dilated=np.zeros_like(actual)
        for dy in range(3):
            for dx in range(3):dilated|=padded[dy:dy+actual.shape[0],dx:dx+actual.shape[1]]
        for y in range(0,25,2):
            for x in range(0,25,2):
                part=dilated[y:y+36,x:x+78];raw=actual[y:y+36,x:x+78]
                if part.shape!=expected.shape:continue
                if .65<raw.sum()/expected.sum()<1.4 and (expected&part).sum()/expected.sum()>.86:return True
    return False


def classify_color(rgb, palette):
    rgb=np.asarray(rgb,dtype=float)/255
    hue,sat,value=colorsys.rgb_to_hsv(*rgb)
    if sat<.45 or value<.33:
        return None
    def distance(candidate):
        d=abs(candidate-hue)
        return min(d,1-d)
    piece=min(palette,key=lambda p:distance(palette[p]))
    return piece if distance(palette[piece])<.065 else None


def countdown_overlay(a,geom):
    """Large yellow countdown glyphs, distinct from a two-cell O sprite."""
    x1=max(0,round(geom.left+geom.cell));x2=min(a.shape[1],round(geom.right-geom.cell))
    y1=max(0,round(geom.top+5*geom.cell));y2=min(a.shape[0],round(geom.top+15*geom.cell))
    part=a[y1:y2,x1:x2].astype(np.int16)
    if not part.size:return False
    mask=(part[:,:,0]>85)&(part[:,:,1]>.55*part[:,:,0])&(part[:,:,2]<.3*part[:,:,0])
    return any(box[3]-box[1]>2.6*geom.cell for box in component_boxes(mask))


def read_state(image, geom=None, palette=None, expected_board=None,game_mode=None,ignore_countdown=False):
    geom=geom or detect_geometry(image)
    if image.size!=(geom.width,geom.height):
        raise ValueError("游戏窗口尺寸发生变化，请重新校准。")
    a=np.asarray(image)
    has_countdown=ignore_countdown and countdown_overlay(a,geom)
    previews=read_previews(image,geom,a)
    palette=dict(palette or DEFAULT_HUES)
    for preview in previews:
        palette[preview["piece"]]=preview["hue"]
    rows=[list("__________") for _ in range(24)]
    # Sample all grid patches in one batch. Hundreds of individual median
    # and colorsys calls were spending the live frame budget on Python.
    yy,xx=np.indices((24,10));py=np.rint(geom.bottom-(yy+.5)*geom.cell).astype(int)
    px=np.rint(geom.left+(xx+.5)*geom.cell).astype(int)
    valid=(py>=0)&(py<a.shape[0])&(px>=0)&(px<a.shape[1])
    radius=max(2,int(geom.cell*.08));dy,dx=np.meshgrid(np.arange(-radius,radius),np.arange(-radius,radius),indexing='ij')
    samples=a[np.clip(py[...,None]+dy.ravel(),0,a.shape[0]-1),np.clip(px[...,None]+dx.ravel(),0,a.shape[1]-1)]
    rgb=np.median(samples,axis=2);hi=rgb.max(2);lo=rgb.min(2);delta=hi-lo;safe=np.maximum(delta,1)
    hue=np.zeros_like(hi);red=hi==rgb[:,:,0];green=(hi==rgb[:,:,1])&~red;blue=~red&~green
    hue[red]=((rgb[:,:,1]-rgb[:,:,2])/safe)[red]%6
    hue[green]=((rgb[:,:,2]-rgb[:,:,0])/safe+2)[green]
    hue[blue]=((rgb[:,:,0]-rgb[:,:,1])/safe+4)[blue];hue/=6
    names=list(palette);dist=np.abs(hue[...,None]-np.array([palette[n] for n in names]));dist=np.minimum(dist,1-dist)
    choice=dist.argmin(2);best=dist.min(2)
    valid&=(delta/np.maximum(hi,1)>=.45)&(hi>=.33*255)&(best<.065)&((yy<20)|(hi>=180))
    for y,x in zip(*np.nonzero(valid)):
        name=names[choice[y,x]]
        if has_countdown and 5<=y<=14 and 1<=x<=8 and name=='O':continue
        rows[y][x]=name
    spawn_points=[(x,y,rows[y][x]) for y in range(24) for x in range(10)
                  if rows[y][x]!="_" and
                  ((expected_board is not None and expected_board[y][x]=="_") or
                   (expected_board is None and y>=20))]
    active=None
    # An empty field's four colored cells can already be below the hidden
    # rows when gravity is enabled. A locked-field reference separates the
    # active sprite anywhere in the board without guessing at stacked cells.
    all_points=[(x,y,rows[y][x]) for y in range(24) for x in range(10) if rows[y][x]!='_']
    if expected_board is None and len(all_points)==4:spawn_points=all_points
    # A PC field occupies at most six bottom rows. An isolated four-cell
    # sprite above row eight is unambiguous even without a prior board,
    # including when a previous piece has automatically locked below it.
    if len(spawn_points)!=4:
        high=[p for p in all_points if p[1]>=8]
        low=[p for p in all_points if p[1]<8]
        if len(high)==4 and max((p[1] for p in low),default=-1)<=6:spawn_points=high
    if expected_board is not None and len(spawn_points)!=4:
        hidden=[p for p in spawn_points if p[1]>=20]
        if len(hidden)==4:spawn_points=hidden
    if (len(spawn_points)==4 and len({p[2] for p in spawn_points})==1 and
            poses_for(spawn_points[0][2],[(x,y) for x,y,_ in spawn_points])):
        active=spawn_points[0][2]
        for x,y,_ in spawn_points:rows[y][x]="_"
    else:spawn_points=[]
    # Hold is color-coded; use robust saturated-pixel hue rather than shape,
    # since used Holds can be dimmed and occupy a different sprite anchor.
    hx1=int(geom.left-5.2*geom.cell);hx2=int(geom.left-.1*geom.cell)
    hy1=int(geom.top+.8*geom.cell);hy2=int(geom.top+3.8*geom.cell)
    hold_region=a[max(0,hy1):hy2,max(0,hx1):hx2]
    hold_mask=colorful(hold_region)
    held=None
    if hold_mask.sum()>geom.cell**2*.5:
        rgb=np.median(hold_region[hold_mask],axis=0)
        held=classify_color(rgb,palette)
    gray=False
    if held is None:
        held=gray_hold_piece(hold_region,geom.cell)
        gray=held is not None
    return {"board":tuple("".join(row) for row in rows),"active":active,
            "active_cells":[(x,y) for x,y,_ in spawn_points],
            "hold":held,"hold_available":not gray,"game_mode":game_mode or ("zen" if is_zen(image) else "practice"),
            "next":"".join(p["piece"] for p in previews),
            "palette":palette,"geometry":geom.to_dict(),"preview_count":len(previews)}
