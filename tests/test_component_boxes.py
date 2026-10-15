from collections import deque
import unittest
import numpy as np
from pc_lab.vision import component_boxes


def pixel_reference(mask,min_area):
    seen=set();boxes=[];h,w=mask.shape
    for y in range(h):
        for x in range(w):
            if not mask[y,x] or (x,y) in seen:continue
            todo=deque([(x,y)]);seen.add((x,y));points=[]
            while todo:
                point=todo.popleft();points.append(point);px,py=point
                for nx,ny in ((px-1,py),(px+1,py),(px,py-1),(px,py+1)):
                    if 0<=nx<w and 0<=ny<h and mask[ny,nx] and (nx,ny) not in seen:
                        seen.add((nx,ny));todo.append((nx,ny))
            if len(points)>=min_area:
                xs,ys=zip(*points);boxes.append((min(xs),min(ys),max(xs)+1,max(ys)+1,len(points)))
    return sorted(boxes,key=lambda b:(b[1],b[0]))


class ComponentBoxTests(unittest.TestCase):
    def test_all_three_by_three_masks_agree_with_pixel_flood_fill(self):
        for bits in range(512):
            mask=np.array([(bits>>i)&1 for i in range(9)],dtype=bool).reshape(3,3)
            for minimum in (1,3):
                self.assertEqual(component_boxes(mask,minimum),pixel_reference(mask,minimum))

    def test_blank_rows_do_not_join_separate_preview_sprites(self):
        mask=np.zeros((160,80),dtype=bool)
        mask[2:7,3:18]=True;mask[99:108,3:18]=True
        mask[106:109,17:22]=True
        self.assertEqual(component_boxes(mask),pixel_reference(mask,10))
        self.assertEqual(component_boxes(np.zeros((0,5),dtype=bool)),[])


if __name__=='__main__':unittest.main()
