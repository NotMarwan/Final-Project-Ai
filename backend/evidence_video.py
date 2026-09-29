"""Bounded, browser-compatible evidence video encoding.

The evidence path is intentionally strict: a clip is either H.264/yuv420p with a
fast-start MP4 layout, or encoding fails.  MPEG-4 Part 2 output is not published
as though it were browser compatible.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Iterable, Optional

import cv2
import numpy as np


class EvidenceVideoError(RuntimeError):
    """Base class for errors safe to classify in evidence audit records."""

    code = "evidence_video_error"


class EvidenceEncoderUnavailable(EvidenceVideoError):
    code = "ffmpeg_unavailable"


class EvidenceEncodingTimeout(EvidenceVideoError):
    code = "ffmpeg_timeout"


class EvidenceEncodingCancelled(EvidenceVideoError):
    code = "ffmpeg_cancelled"


class EvidenceOutputInvalid(EvidenceVideoError):
    code = "invalid_browser_mp4"


@dataclass(frozen=True)
class EvidenceVideoResult:
    codec: str
    pixel_format: str
    frame_count: int
    width: int
    height: int
    fps: float
    fast_start: bool
    encoder: str


# Encoder opt-in (E-7). NVENC is opt-in: an unset variable keeps the validated
# CPU path. "auto" probes NVENC capability and prefers it with a safe libx264
# fallback; "h264_nvenc" forces the hardware path and fails loudly without one.
EVIDENCE_ENCODER_ENV = "AI_SENTINEL_EVIDENCE_ENCODER"
_ENCODER_MODES = ("auto", "libx264", "h264_nvenc")
# Validated by E-7: 2 concurrent NVENC encode sessions on the campaign GPU.
_NVENC_SESSION_LIMIT = 2
_nvenc_slots = threading.BoundedSemaphore(_NVENC_SESSION_LIMIT)
_nvenc_probe_lock = threading.Lock()
_nvenc_probe_cache: dict[str, bool] = {}


def resolve_encoder_mode() -> str:
    raw = os.getenv(EVIDENCE_ENCODER_ENV, "").strip().lower()
    if not raw:
        return "libx264"
    if raw not in _ENCODER_MODES:
        raise EvidenceEncoderUnavailable(
            f"{EVIDENCE_ENCODER_ENV} must be one of auto|libx264|h264_nvenc"
        )
    return raw


def _probe_nvenc(ffmpeg: Path) -> bool:
    """One-frame capability probe; cached per ffmpeg binary. Never downloads."""
    key = str(ffmpeg)
    with _nvenc_probe_lock:
        cached = _nvenc_probe_cache.get(key)
        if cached is not None:
            return cached
        command = [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=black:s=64x64:d=0.04:r=25",
            "-frames:v",
            "1",
            "-c:v",
            "h264_nvenc",
            "-f",
            "null",
            "-",
        ]
        try:
            completed = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=False,
                timeout=10.0,
                creationflags=_creation_flags(),
            )
            usable = completed.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            usable = False
        _nvenc_probe_cache[key] = usable
        return usable


def _encoder_video_args(encoder: str) -> list[str]:
    if encoder == "libx264":
        return [
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-profile:v", "high",
            "-tag:v", "avc1",
        ]
    if encoder == "h264_nvenc":
        return [
            "-c:v", "h264_nvenc",
            "-preset", "p4",
            "-cq", "23",
            "-b:v", "0",
            "-pix_fmt", "yuv420p",
            "-profile:v", "high",
            "-tag:v", "avc1",
        ]
    raise ValueError(f"unsupported evidence encoder: {encoder}")


def resolve_ffmpeg() -> Path:
    """Resolve an installed ffmpeg without downloading or invoking a shell."""
    configured = os.getenv("AI_SENTINEL_FFMPEG")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_file():
            raise EvidenceEncoderUnavailable(
                "AI_SENTINEL_FFMPEG does not name an existing file"
            )
        return path.resolve()

    system = shutil.which("ffmpeg")
    if system:
        return Path(system).resolve()

    try:
        import imageio_ffmpeg

        bundled = Path(imageio_ffmpeg.get_ffmpeg_exe())
        if bundled.is_file():
            return bundled.resolve()
    except (ImportError, OSError, RuntimeError):
        pass

    # A virtual environment may not expose an imageio-ffmpeg package installed
    # beside its base interpreter.  Reuse only that package's well-known bundled
    # binary directory; do not crawl arbitrary paths or download an executable.
    bundled_dir = Path(sys.base_prefix) / "Lib" / "site-packages" / "imageio_ffmpeg" / "binaries"
    if bundled_dir.is_dir():
        candidates = sorted(bundled_dir.glob("ffmpeg-*.exe" if os.name == "nt" else "ffmpeg-*"))
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()

    raise EvidenceEncoderUnavailable(
        "ffmpeg is unavailable; install it or set AI_SENTINEL_FFMPEG to an executable"
    )


def _creation_flags() -> int:
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0


def _stderr_text(log) -> str:
    log.seek(0)
    return log.read().decode("utf-8", errors="replace")[-4000:].strip()


def _kill_and_join(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.kill()
    try:
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired as exc:
        raise EvidenceVideoError("ffmpeg could not be stopped") from exc


def _encode_raw_frames(
    command: list[str],
    frames: Iterable[np.ndarray],
    *,
    timeout_seconds: float,
    cancel_event: Optional[threading.Event],
) -> str:
    """Stream frames while a joined watchdog bounds blocked pipe writes."""
    if cancel_event is not None and cancel_event.is_set():
        raise EvidenceEncodingCancelled("evidence encoding cancelled before start")

    with tempfile.TemporaryFile() as error_log:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=error_log,
            shell=False,
            creationflags=_creation_flags(),
        )
        finished = threading.Event()
        interruption: list[str] = []
        deadline = time.monotonic() + timeout_seconds

        def watchdog() -> None:
            while not finished.wait(0.05):
                if cancel_event is not None and cancel_event.is_set():
                    interruption.append("cancelled")
                    _kill_and_join(process)
                    return
                if time.monotonic() >= deadline:
                    interruption.append("timeout")
                    _kill_and_join(process)
                    return

        guard = threading.Thread(
            target=watchdog,
            daemon=False,
            name="evidence-video-watchdog",
        )
        guard.start()
        caught: Optional[BaseException] = None
        try:
            assert process.stdin is not None
            for frame in frames:
                process.stdin.write(frame.tobytes())
            process.stdin.close()
            process.wait()
        except (BrokenPipeError, OSError) as exc:
            caught = exc
            _kill_and_join(process)
        finally:
            finished.set()
            guard.join(timeout=2.0)
            if guard.is_alive():
                _kill_and_join(process)
                raise EvidenceVideoError("ffmpeg watchdog did not stop")

        details = _stderr_text(error_log)
        if interruption:
            if interruption[0] == "cancelled":
                raise EvidenceEncodingCancelled("evidence encoding cancelled")
            raise EvidenceEncodingTimeout(
                f"evidence encoding exceeded {timeout_seconds:.1f} seconds"
            )
        if caught is not None or process.returncode != 0:
            suffix = f": {details}" if details else ""
            raise EvidenceVideoError(f"ffmpeg H.264 encoding failed{suffix}") from caught
        return details


def _prepare_frame(frame: np.ndarray, width: int, height: int) -> np.ndarray:
    if not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError("evidence frames must be HxWx3 numpy arrays")
    if frame.dtype != np.uint8:
        raise ValueError("evidence frames must use uint8 BGR pixels")
    if frame.shape[:2] != (height, width):
        frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
    if height % 2 or width % 2:
        frame = cv2.copyMakeBorder(
            frame,
            0,
            height % 2,
            0,
            width % 2,
            cv2.BORDER_REPLICATE,
        )
    return np.ascontiguousarray(frame)


def _mp4_box_positions(path: Path) -> dict[bytes, int]:
    positions: dict[bytes, int] = {}
    file_size = path.stat().st_size
    with path.open("rb") as source:
        offset = 0
        while offset + 8 <= file_size:
            source.seek(offset)
            header = source.read(16)
            if len(header) < 8:
                break
            size = int.from_bytes(header[:4], "big")
            kind = header[4:8]
            header_size = 8
            if size == 1:
                if len(header) < 16:
                    break
                size = int.from_bytes(header[8:16], "big")
                header_size = 16
            elif size == 0:
                size = file_size - offset
            if size < header_size or offset + size > file_size:
                raise EvidenceOutputInvalid("MP4 contains an invalid top-level box")
            positions.setdefault(kind, offset)
            offset += size
    return positions


def _probe_output(
    ffmpeg: Path,
    path: Path,
    *,
    expected_frames: int,
    timeout_seconds: float,
) -> tuple[int, str]:
    command = [
        str(ffmpeg),
        "-hide_banner",
        "-nostdin",
        "-i",
        str(path),
        "-map",
        "0:v:0",
        "-an",
        "-f",
        "null",
        "-",
        "-progress",
        "pipe:1",
        "-nostats",
    ]
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            timeout=timeout_seconds,
            creationflags=_creation_flags(),
        )
    except subprocess.TimeoutExpired as exc:
        raise EvidenceEncodingTimeout("evidence decode verification timed out") from exc
    diagnostics = completed.stderr.decode("utf-8", errors="replace")
    progress = completed.stdout.decode("utf-8", errors="replace")
    if completed.returncode != 0:
        raise EvidenceOutputInvalid(
            "encoded evidence failed full decode: " + diagnostics[-2000:].strip()
        )
    frames = [int(value) for value in re.findall(r"(?m)^frame=(\d+)\s*$", progress)]
    decoded = frames[-1] if frames else 0
    if decoded != expected_frames:
        raise EvidenceOutputInvalid(
            f"encoded evidence decoded {decoded} of {expected_frames} frames"
        )
    normalized = diagnostics.lower()
    if "video: h264" not in normalized or "yuv420p" not in normalized:
        raise EvidenceOutputInvalid("encoded evidence is not H.264 with yuv420p pixels")
    return decoded, diagnostics


def encode_browser_mp4(
    frames: Iterable[np.ndarray],
    output_path: Path,
    *,
    fps: float,
    width: int,
    height: int,
    timeout_seconds: float = 12.0,
    cancel_event: Optional[threading.Event] = None,
    encoder: Optional[str] = None,
) -> EvidenceVideoResult:
    """Encode and fully verify an H.264/yuv420p fast-start MP4.

    ``output_path`` should be an unpublished temporary path.  Publication and
    chain-of-custody recording remain the caller's responsibility.

    Encoder selection (E-7): ``encoder`` overrides ``AI_SENTINEL_EVIDENCE_ENCODER``
    (``auto`` | ``libx264`` | ``h264_nvenc``). An unset variable keeps the
    validated CPU encoder; ``auto`` probes NVENC capability and falls back to
    libx264 on any failure; ``h264_nvenc`` is a strict opt-in. The verified
    output contract and ``EvidenceVideoResult`` fields are encoder-agnostic and
    ``result.encoder`` reports the encoder that actually ran.
    """
    output_path = Path(output_path)
    if not output_path.parent.is_dir():
        raise ValueError("evidence output directory does not exist")
    fps = float(fps)
    width, height = int(width), int(height)
    timeout_seconds = float(timeout_seconds)
    if not 1.0 <= fps <= 120.0:
        raise ValueError("evidence fps must be between 1 and 120")
    if width <= 0 or height <= 0:
        raise ValueError("evidence dimensions must be positive")
    if not 0.1 <= timeout_seconds <= 60.0:
        raise ValueError("evidence timeout must be between 0.1 and 60 seconds")

    materialized = list(frames)
    if not materialized:
        raise ValueError("no evidence frames")
    if len(materialized) > 2000:
        raise ValueError("evidence frame count exceeds the bounded limit")
    encoded_width = width + width % 2
    encoded_height = height + height % 2
    prepared = [_prepare_frame(frame, width, height) for frame in materialized]
    ffmpeg = resolve_ffmpeg()
    mode = (encoder or resolve_encoder_mode()).strip().lower()
    if mode not in _ENCODER_MODES:
        raise ValueError(f"unsupported evidence encoder: {mode}")

    def build_command(encoder_name: str) -> list[str]:
        return [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-f",
            "rawvideo",
            "-pixel_format",
            "bgr24",
            "-video_size",
            f"{encoded_width}x{encoded_height}",
            "-framerate",
            f"{fps:.6f}",
            "-i",
            "pipe:0",
            "-an",
            *_encoder_video_args(encoder_name),
            "-movflags",
            "+faststart",
            "-frames:v",
            str(len(prepared)),
            str(output_path),
        ]

    def run(encoder_name: str) -> int:
        # The decode probe + fast-start checks are encoder-agnostic: the
        # published output contract (H.264/yuv420p/fast-start, exact frame
        # count) is identical for every encoder, so SC-8 integrity holds.
        _encode_raw_frames(
            build_command(encoder_name),
            prepared,
            timeout_seconds=timeout_seconds,
            cancel_event=cancel_event,
        )
        boxes = _mp4_box_positions(output_path)
        fast_start = b"moov" in boxes and b"mdat" in boxes and boxes[b"moov"] < boxes[b"mdat"]
        if not fast_start:
            raise EvidenceOutputInvalid("encoded evidence is missing fast-start MP4 layout")
        decoded, _ = _probe_output(
            ffmpeg,
            output_path,
            expected_frames=len(prepared),
            timeout_seconds=min(timeout_seconds, 10.0),
        )
        return decoded

    chosen = "libx264"
    allow_fallback = False
    slot_acquired = False
    if mode == "h264_nvenc":
        # Explicit hardware opt-in: fail loudly rather than silently degrade.
        if not _nvenc_slots.acquire(timeout=timeout_seconds):
            raise EvidenceEncoderUnavailable("h264_nvenc session capacity is exhausted")
        slot_acquired = True
        chosen = "h264_nvenc"
    elif mode == "auto":
        # Capability-based opt-in with the validated CPU path as fallback.
        if _probe_nvenc(ffmpeg) and _nvenc_slots.acquire(blocking=False):
            slot_acquired = True
            chosen, allow_fallback = "h264_nvenc", True

    try:
        try:
            decoded = run(chosen)
        except (EvidenceEncodingTimeout, EvidenceEncodingCancelled):
            raise
        except EvidenceVideoError:
            if not (allow_fallback and chosen == "h264_nvenc"):
                raise
            if slot_acquired:
                _nvenc_slots.release()
                slot_acquired = False
            chosen = "libx264"
            decoded = run(chosen)
    except Exception:
        try:
            output_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    finally:
        if slot_acquired:
            _nvenc_slots.release()
    return EvidenceVideoResult(
        codec="h264",
        pixel_format="yuv420p",
        frame_count=decoded,
        width=encoded_width,
        height=encoded_height,
        fps=fps,
        fast_start=True,
        encoder=f"ffmpeg/{chosen}",
    )
