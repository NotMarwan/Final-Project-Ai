"""WebRTC streaming support for sub-100ms latency video delivery.

Requires: pip install aiortc av

Usage:
    from webrtc_streamer import WebRTCManager
    manager = WebRTCManager()

    @app.post("/webrtc/offer/{camera_id}")
    async def offer(camera_id: str, request: Request):
        data = await request.json()
        return await manager.handle_offer(camera_id, frame_getter, data["sdp"], data["type"])
"""
from __future__ import annotations

import asyncio
from typing import Callable, Optional

import cv2
import numpy as np

try:
    from aiortc import RTCPeerConnection, VideoStreamTrack
    from av import VideoFrame
    _WEBRTC_AVAILABLE = True
except ImportError:
    _WEBRTC_AVAILABLE = False
    VideoStreamTrack = object


class FrameVideoTrack(VideoStreamTrack):
    """A video track that serves the latest frame from a getter function."""
    kind = "video"

    def __init__(self, frame_getter: Callable[[], Optional[bytes]]):
        super().__init__()
        self.frame_getter = frame_getter

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        frame_data = self.frame_getter()

        if frame_data is None:
            img = np.zeros((720, 1280, 3), dtype=np.uint8)
        elif isinstance(frame_data, bytes):
            img = cv2.imdecode(np.frombuffer(frame_data, np.uint8), cv2.IMREAD_COLOR)
        else:
            img = frame_data

        if img.shape[2] == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        elif img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)

        frame = VideoFrame.from_ndarray(img, format="rgb24")
        frame.pts = pts
        frame.time_base = time_base
        return frame


class WebRTCManager:
    def __init__(self):
        self.pcs: dict[str, RTCPeerConnection] = {}
        self.available = _WEBRTC_AVAILABLE

    async def handle_offer(
        self,
        camera_id: str,
        frame_getter: Callable[[], Optional[bytes]],
        sdp: str,
        type_: str,
    ) -> dict:
        if not self.available:
            return {"error": "WebRTC not available. Install: pip install aiortc av"}

        pc = RTCPeerConnection()
        self.pcs[camera_id] = pc

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            if pc.connectionState in ("failed", "closed"):
                await pc.close()
                self.pcs.pop(camera_id, None)

        video_track = FrameVideoTrack(frame_getter)
        pc.addTrack(video_track)
        await pc.setRemoteDescription({"sdp": sdp, "type": type_})
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}

    async def close(self, camera_id: str):
        pc = self.pcs.pop(camera_id, None)
        if pc:
            await pc.close()

    async def close_all(self):
        for camera_id in list(self.pcs.keys()):
            await self.close(camera_id)
