"""Equivalent nearest-neighbour scaling before copying a DXGI BGRA frame.

The pixel index maps come from Pillow itself. The returned RGB pixels match
the former full-size RGB decode followed by Pillow NEAREST resize.
"""
from functools import lru_cache
import numpy as np
from PIL import Image


@lru_cache(maxsize=32)
def _nearest_indices(width,height,target_width,target_height):
    xs=np.asarray(Image.fromarray(np.arange(width,dtype=np.int32).reshape(1,width)).resize(
        (target_width,1),Image.Resampling.NEAREST)).reshape(-1).copy()
    ys=np.asarray(Image.fromarray(np.arange(height,dtype=np.int32).reshape(height,1)).resize(
        (1,target_height),Image.Resampling.NEAREST)).reshape(-1).copy()
    xs.flags.writeable=False;ys.flags.writeable=False
    return xs,ys


def dxgi_image(frame,size):
    if frame.ndim!=3 or frame.shape[2]!=4 or frame.dtype!=np.uint8:
        raise ValueError('DXGI frame must contain uint8 BGRA pixels.')
    height,width=frame.shape[:2]
    if (width,height)!=size:
        if frame.flags.c_contiguous:
            # Label the bytes RGBA only to borrow Pillow's zero-copy buffer
            # mapper. NEAREST does not blend or interpret alpha; decode the
            # resulting bytes as their actual BGRA order afterwards.
            mapped=Image.frombuffer('RGBA',(width,height),frame,'raw','RGBA',0,1)
            small=mapped.resize(size,Image.Resampling.NEAREST)
            return Image.frombytes('RGB',size,small.tobytes(),'raw','BGRX')
        xs,ys=_nearest_indices(width,height,*size)
        frame=frame[ys[:,None],xs[None,:]]
    return Image.frombytes('RGB',size,frame.tobytes(),'raw','BGRX')
