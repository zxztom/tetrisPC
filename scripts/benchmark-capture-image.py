"""Pixel equivalence and copy/resize timing only; never captures the desktop."""
import argparse,json,statistics,sys,time
from pathlib import Path
import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from pc_lab.capture_image import dxgi_image


def reference(frame,size):
    image=Image.frombytes('RGB',(frame.shape[1],frame.shape[0]),frame.tobytes(),'raw','BGRX')
    return image.resize(size,Image.Resampling.NEAREST) if image.size!=size else image


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();rng=np.random.default_rng(482);reports=[]
    for width,height in ((3072,1920),(2200,1800),(1536,960)):
        frame=rng.integers(0,256,(height,width,4),dtype=np.uint8);size=(round(width*.4),round(height*.4))
        assert reference(frame,size).tobytes()==dxgi_image(frame,size).tobytes()
        values={'full_decode_then_resize':[],'resize_before_copy':[]}
        for n in range(30):
            pairs=[('full_decode_then_resize',reference),('resize_before_copy',dxgi_image)]
            if n%2:pairs.reverse()
            for name,fn in pairs:
                start=time.perf_counter();fn(frame,size);values[name].append((time.perf_counter()-start)*1000)
        reports.append(dict(source=[width,height],target=list(size),pixels_identical=True,
            timings={k:dict(median_ms=statistics.median(v),mean_ms=statistics.mean(v)) for k,v in values.items()}))
    a.output.write_text(json.dumps(dict(reports=reports,native_verified=False,
        warning='Synthetic BGRA pixels; only image conversion is timed. Not whole capture or game PPS.'),indent=2),encoding='utf-8')
    print(json.dumps(reports))


if __name__=='__main__':main()
