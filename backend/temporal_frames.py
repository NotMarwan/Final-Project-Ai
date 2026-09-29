"""Timestamped immutable frame envelopes and explicit window validity."""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
import math
import time
import numpy as np

@dataclass
class FramePacket:
    frame: np.ndarray
    sequence: int
    captured_at: float
    source_width: int
    source_height: int
    source_fps: float
    decision_config: dict = field(default_factory=dict)
    # Prerecorded media timeline only; captured_at remains the actual read clock.
    sample_timestamp: float | None = None
    # Construction clock (monotonic, producer process) for stage timing:
    # stageCaptureToQueueMs = enqueued_at - captured_at (producer side),
    # stageEnqueueToDequeueMs = dequeue - enqueued_at (IPC + bounded queue wait).
    # Defaults to construction time; pass explicitly only if the packet is
    # built well before it is put on the queue.
    enqueued_at: float | None = None
    # Same construction instant on the QPC clock (time.perf_counter). Pairs
    # with producer stamps declared as capture_clock_base="perf-qpc"; never
    # subtract across bases (see inference_process._queue_policy_config).
    enqueued_at_qpc: float | None = None

    def __post_init__(self):
        if self.enqueued_at is None:
            self.enqueued_at = time.monotonic()
        if self.enqueued_at_qpc is None:
            self.enqueued_at_qpc = time.perf_counter()

    @property
    def nbytes(self):
        return self.frame.nbytes


class TemporalWindow:
    """Keep source timestamps; do not turn missing frames into fake samples."""
    def __init__(self, frames=32, nominal_fps=30.0, tolerance=.10):
        if frames<2 or not math.isfinite(nominal_fps) or nominal_fps<=0:
            raise ValueError('Invalid temporal sampling contract')
        self.frames=frames
        self.fps=nominal_fps
        self.tolerance=tolerance
        self.samples=deque(maxlen=frames)

    def push(self, stamp, frame):
        if not math.isfinite(stamp) or (self.samples and stamp<=self.samples[-1][0]):
            return False
        self.samples.append((stamp,frame))
        return True

    def status(self):
        span=self.samples[-1][0]-self.samples[0][0] if len(self.samples)>1 else 0.0
        nominal=(self.frames-1)/self.fps
        gaps=[b[0]-a[0] for a,b in zip(self.samples,list(self.samples)[1:])]
        valid=len(self.samples)==self.frames and abs(span-nominal)<=nominal*self.tolerance and max(gaps,default=0)<=2.1/self.fps
        return {'frames_collected':len(self.samples),'frames_required':self.frames,
                'span_seconds':span,'nominal_span_seconds':nominal,'valid':valid}

    def frames_snapshot(self):
        return [frame for _,frame in self.samples]


def downscale_for_inference(frame,max_side=640):
    import cv2
    height,width=frame.shape[:2]
    scale=min(1.0,max_side/max(height,width))
    if scale==1.0:
        return frame
    return cv2.resize(frame,(max(1,round(width*scale)),max(1,round(height*scale))),interpolation=cv2.INTER_AREA)
