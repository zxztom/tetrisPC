"""Compare preview recognizers on saved native screenshots, without input."""
import json,sys,time,statistics
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from pc_lab.vision import read_state,Geometry
from pc_lab.engine import empty_board
from pc_lab.solver import ROOT


def legacy_components(mask,min_area=10):
    padded=np.pad(np.asarray(mask,dtype=bool),((0,0),(1,1)))
    edges=padded[:,1:]!=padded[:,:-1];parents=[];spans=[];previous=[]
    def root(i):
        while parents[i]!=i:parents[i]=parents[parents[i]];i=parents[i]
        return i
    for y in range(mask.shape[0]):
        ends=np.flatnonzero(edges[y]);current=[];offset=0
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


fixtures=[]
for folder in ('live-20261015-124134-19a712b0','live-20261015-091434-81773486','live-20261015-133329-cced7b92'):
    base=ROOT/'output'/folder;session=json.loads((base/'session.json').read_text(encoding='utf-8'))
    for file in sorted(base.glob('pc-*.png')):
        image=Image.open(file).convert('RGB');image.load()
        fixtures.append((image,Geometry(**session['geometry']),str(file)))

def run():
    states=[];durations=[]
    for image,geometry,_ in fixtures:
        began=time.perf_counter();states.append(read_state(image,geometry,expected_board=empty_board(),game_mode='practice'))
        durations.append(time.perf_counter()-began)
    return states,dict(mean_ms=1000*statistics.mean(durations),median_ms=1000*statistics.median(durations),
                       total_ms=1000*sum(durations))

with patch('pc_lab.vision.component_boxes',legacy_components):previous,old=run()
current,new=run()
if previous!=current:raise RuntimeError('Saved native screenshot recognition changed')
report=dict(fixtures=len(fixtures),old=old,new=new,all_observations_identical=True,
            capture_time_included=False,native_game_run=False,fixtures_paths=[p for _,__,p in fixtures])
(ROOT/'output/vision-components-benchmark.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='fixtures_paths'}))

# These files were captured at scale .5. Simulate smaller raster sizes
# offline before considering a different native capture scale.
scaled=[]
semantic_keys=('board','active','active_cells','hold','hold_available','next','game_mode','preview_count')
for ratio in (.8,.7,.6):
    durations=[];differences=[]
    for baseline,(image,g,path) in zip(current,fixtures):
        size=(round(image.width*ratio),round(image.height*ratio))
        reduced=image.resize(size,Image.Resampling.NEAREST)
        geometry=Geometry(g.left*ratio,g.top*ratio,g.cell*ratio,*size)
        began=time.perf_counter()
        try:
            observed=read_state(reduced,geometry,expected_board=empty_board(),game_mode='practice')
            changed=[key for key in semantic_keys if observed[key]!=baseline[key]]
            if changed:differences.append(dict(path=path,reason='observation differs',changed=changed))
        except ValueError as exc:differences.append(dict(path=path,reason=str(exc)))
        durations.append(time.perf_counter()-began)
    scaled.append(dict(simulated_capture_scale=.5*ratio,fixtures=len(fixtures),
        observation_differences=differences,mean_recognition_ms=1000*statistics.mean(durations),
        compared_keys=semantic_keys,native_capture_test=False,
        pixel_resampling='offline Pillow nearest; geometry/palette may change, actual GDI/DXGI still needs native validation'))
(ROOT/'output/vision-capture-scale-benchmark.json').write_text(json.dumps(scaled,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps([{k:v for k,v in r.items() if k!='observation_differences'}|dict(differences=len(r['observation_differences'])) for r in scaled]))
