"""WebRTC streaming support for sub-100ms latency video delivery.

Requires: pip install aiortc av

Usage:
    from webrtc_streamer import WebRTCManager
    manager = WebRTCManager()

    @app.post("/webrtc/offer/{camera_id}")
    async def offer(camera_id: str, request: Request):
        data = await request.json()
        return await manager.handle_offer(camera_id, frame_getter, data["sdp"], data["type"])

WT-17 (S-09, F-37) adds ``Go2RTCSidecar``: the recommended WebRTC/MSE path from
WT-05/WT-10 is the upstream MIT go2rtc binary (native win64 zip) wrapped behind an
explicit DISABLED health state when it is absent (SC-10 pattern). ``webrtc.enabled``
defaults to false until a measured WebRTC latency row exists (E-5); the MJPEG
baseline is always retained. The binary is never committed (.gitignore: go2rtc*).
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import hashlib
import os
import subprocess
import time
from typing import Any, Callable, Optional

import cv2
import numpy as np

try:
    from aiortc import RTCPeerConnection, VideoStreamTrack
    from av import VideoFrame
    _WEBRTC_AVAILABLE = True
except ImportError:
    _WEBRTC_AVAILABLE = False
    VideoStreamTrack = object


# Provenance for the optional sidecar (never committed; provisioned out-of-band).
GO2RTC_UPSTREAM = "https://github.com/AlexxIT/go2rtc"
GO2RTC_WIN64_ZIP = "go2rtc_win64.zip (upstream release asset)"
GO2RTC_LICENSE = "MIT — upstream AlexxIT/go2rtc (LICENSE at the repository root)"

_DISABLED_DEFAULT_REASON = (
    "webrtc.enabled is false: no measured WebRTC latency row exists yet (E-5); "
    "the MJPEG baseline is retained"
)


class Go2RTCSidecar:
    """Optional go2rtc sidecar with explicit, never-silent health (SC-10 pattern).

    States: DISABLED (not enabled / binary absent), READY (binary usable),
    RUNNING (launched), ERROR (hash mismatch or launch failure).
    """

    def __init__(self, config: Optional[dict[str, Any]] = None, environ: Optional[dict[str, str]] = None):
        env = os.environ if environ is None else environ
        webrtc = (config or {}).get("webrtc") or {}
        self.enabled = bool(webrtc.get("enabled", False))
        self.binary = env.get("AI_SENTINEL_GO2RTC_BIN") or str(webrtc.get("go2rtc_binary") or "")
        self.config_path = str(webrtc.get("go2rtc_config") or "")
        try:
            self.port = int(webrtc.get("port", 1984))
        except (TypeError, ValueError):
            self.port = 1984
        self.expected_sha256 = (env.get("AI_SENTINEL_GO2RTC_SHA256") or str(webrtc.get("go2rtc_sha256") or "")).lower()
        self.state = "DISABLED"
        self.reason: Optional[str] = _DISABLED_DEFAULT_REASON if not self.enabled else None
        self.process: Optional[subprocess.Popen] = None
        self.sha256: Optional[str] = None

    def _resolve_binary(self) -> Optional[Path]:
        if not self.binary:
            return None
        candidate = Path(self.binary)
        if candidate.is_absolute():
            return candidate
        return (Path(__file__).resolve().parent / candidate).resolve()

    def check(self) -> str:
        """Resolve the health state without launching anything."""
        if not self.enabled:
            self.state, self.reason = "DISABLED", _DISABLED_DEFAULT_REASON
            return self.state
        path = self._resolve_binary()
        if path is None:
            self.state = "DISABLED"
            self.reason = "no go2rtc binary configured (webrtc.go2rtc_binary / AI_SENTINEL_GO2RTC_BIN)"
            return self.state
        if not path.is_file():
            self.state = "DISABLED"
            self.reason = (
                f"go2rtc binary not found at {path}: provision {GO2RTC_WIN64_ZIP} "
                f"from {GO2RTC_UPSTREAM} ({GO2RTC_LICENSE})"
            )
            return self.state
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            self.state = "ERROR"
            self.reason = f"go2rtc binary unreadable: {type(exc).__name__}"
            return self.state
        self.sha256 = digest
        if self.expected_sha256 and digest != self.expected_sha256:
            self.state = "ERROR"
            self.reason = f"go2rtc binary hash mismatch: expected {self.expected_sha256}, found {digest}"
            return self.state
        self.state, self.reason = "READY", None
        return self.state

    def start(self) -> dict[str, Any]:
        if self.check() != "READY":
            return self.health()
        path = self._resolve_binary()
        argv = [str(path)]
        if self.config_path:
            argv += ["-config", str(Path(self.config_path))]
        try:
            self.process = subprocess.Popen(argv, cwd=str(path.parent), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            time.sleep(0.3)
            if self.process.poll() is not None:
                detail = (self.process.stderr.read() or b"")[:200].decode(errors="replace").strip()
                self.state = "ERROR"
                self.reason = f"go2rtc exited immediately (code {self.process.returncode}): {detail}"
                self.process = None
            else:
                self.state, self.reason = "RUNNING", None
        except OSError as exc:
            self.state = "ERROR"
            self.reason = f"go2rtc launch failed: {type(exc).__name__}"
            self.process = None
        return self.health()

    def stop(self) -> None:
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None

    def health(self) -> dict[str, Any]:
        return {
            "module": "go2rtc_sidecar",
            "state": self.state,
            "running": bool(self.process is not None and self.process.poll() is None),
            "reason": self.reason,
            "binary": self.binary or None,
            "sha256": self.sha256,
            "expectedSha256": self.expected_sha256 or None,
            "port": self.port,
            "license": GO2RTC_LICENSE,
            "upstream": GO2RTC_UPSTREAM,
            "artifact": GO2RTC_WIN64_ZIP,
        }



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
