import unittest
import numpy as np
from PIL import Image
from pc_lab.capture_image import dxgi_image


class CaptureImageTests(unittest.TestCase):
    def test_pixel_identical_to_full_decode_then_pillow_resize(self):
        rng=np.random.default_rng(423)  # Synthetic pixels, not a game queue.
        for width,height in ((1,1),(7,9),(43,57),(257,193),(160,90)):
            frame=rng.integers(0,256,(height,width,4),dtype=np.uint8)
            for scale in (.35,.4,.5,1,1.3):
                size=(max(1,round(width*scale)),max(1,round(height*scale)))
                with self.subTest(source=(width,height),target=size):
                    reference=Image.frombytes('RGB',(width,height),frame.tobytes(),'raw','BGRX')
                    if reference.size!=size:reference=reference.resize(size,Image.Resampling.NEAREST)
                    actual=dxgi_image(frame,size)
                    self.assertEqual(actual.size,reference.size)
                    self.assertEqual(actual.tobytes(),reference.tobytes())

    def test_non_contiguous_roi_and_repeated_cached_indices(self):
        frame=np.arange(29*37*4,dtype=np.uint8).reshape(29,37,4)[2:27:2,3:35:2]
        for size in ((6,5),(9,11),(6,5)):
            reference=Image.frombytes('RGB',(frame.shape[1],frame.shape[0]),frame.tobytes(),'raw','BGRX')
            reference=reference.resize(size,Image.Resampling.NEAREST)
            self.assertEqual(dxgi_image(frame,size).tobytes(),reference.tobytes())

    def test_returned_image_does_not_alias_the_reused_capture_buffer(self):
        frame=np.full((90,160,4),87,dtype=np.uint8)
        image=dxgi_image(frame,(64,36));before=image.tobytes()
        frame.fill(0)
        self.assertEqual(image.tobytes(),before)


if __name__=='__main__':unittest.main()
