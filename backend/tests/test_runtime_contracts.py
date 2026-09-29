import importlib.util
from pathlib import Path
import sys
import unittest
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from temporal_frames import TemporalWindow, FramePacket, downscale_for_inference
from local_forensics import build_local_report

class RuntimeContractTests(unittest.TestCase):
    def test_uniform_window_is_valid(self):
        window=TemporalWindow(32,30)
        for i in range(32):window.push(100+i/30,np.zeros((1,1,3)))
        self.assertTrue(window.status()['valid'])

    def test_dropped_time_window_is_invalid(self):
        window=TemporalWindow(32,30)
        for i in range(32):window.push(100+i/15,np.zeros((1,1,3)))
        self.assertFalse(window.status()['valid'])

    def test_duplicate_timestamp_does_not_fill_window(self):
        window=TemporalWindow(32,30)
        for _ in range(40):window.push(100,np.zeros((1,1,3)))
        self.assertEqual(window.status()['frames_collected'],1)

    def test_ipc_downscale_preserves_aspect(self):
        frame=np.zeros((1080,1920,3),dtype=np.uint8)
        small=downscale_for_inference(frame)
        self.assertEqual(small.shape,(360,640,3))
        self.assertLess(small.nbytes,frame.nbytes/8)

    def test_offline_report_does_not_invent_image_description(self):
        text=build_local_report({'id':'alert-test','cameraId':'CAM-01','confidence':float('nan')})
        self.assertIn('لم يُجرَ تحليل لغوي بصري',text)
        self.assertIn('غير متاح',text)
        self.assertNotIn('nan',text)

if __name__=='__main__':unittest.main()
