"""WT-14 E-6 evidence-ring aliasing regression + ring format contract.

Pins: (1) ring payloads never alias the capture buffer (downscale passthrough
must copy), (2) derived inference views never contaminate evidence, (3) ROI
crops are derived on copies, (4) jpeg90/nv12 compressed modes round-trip
through decode-at-assembly without breaking the (stamp, frame) writer
contract, (5) mixed-size windows are fitted WITHOUT upscaling.
"""
import queue

import numpy as np

from temporal_frames import downscale_for_inference
from pipeline_capture import (
    DecodedPostQueue,
    copy_if_aliased,
    decode_evidence_frame,
    fit_evidence_frame,
    iter_evidence_frames,
    make_evidence_frame,
    materialize_evidence_samples,
)


def make_frame(seed, height=540, width=960):
    # smooth gradient + light noise: JPEG-meaningful content (pure uniform
    # noise is a pathological worst case no real camera produces)
    ys = np.linspace(0, 255, height, dtype=np.float32)[:, None]
    xs = np.linspace(0, 255, width, dtype=np.float32)[None, :]
    base = (ys + xs) / 2.0
    rng = np.random.default_rng(seed)
    noise = rng.integers(0, 20, size=(height, width, 3)).astype(np.float32)
    return np.clip(base[:, :, None] + noise, 0, 255).astype(np.uint8)


def test_ring_entry_does_not_alias_capture_buffer_on_passthrough():
    raw = make_frame(1, height=540, width=960)  # max-side 960 -> no resize
    view = downscale_for_inference(raw, 960)
    assert view is raw  # the passthrough that E-6 pins
    entry = make_evidence_frame(view, raw, "bgr", captured_at=1.0, sequence=1)
    assert entry.payload is not raw
    snapshot = entry.payload.copy()
    raw[:, :, :] = 0  # simulate buffer reuse by the capture backend
    assert np.array_equal(entry.payload, snapshot)


def test_ring_entry_fresh_resize_output_is_stored_without_extra_copy():
    raw = make_frame(2, height=720, width=1280)
    view = downscale_for_inference(raw, 960)
    assert view is not raw
    entry = make_evidence_frame(view, raw, "bgr", captured_at=1.0, sequence=1)
    assert entry.payload is view  # zero avoidable copies


def test_inference_view_never_aliases_capture_or_evidence():
    raw = make_frame(3, height=540, width=960)  # <=640? no: 960 -> resize for 640
    small = copy_if_aliased(downscale_for_inference(raw, 640), raw)
    entry = make_evidence_frame(downscale_for_inference(raw, 960), raw, "bgr", 1.0, 1)
    small[:, :, :] = 0
    assert np.any(entry.payload != 0)  # evidence untouched by view mutation
    assert np.any(raw != 0)            # capture buffer untouched as well

    raw_small = make_frame(4, height=360, width=640)  # passthrough case
    small2 = copy_if_aliased(downscale_for_inference(raw_small, 640), raw_small)
    assert small2 is not raw_small
    entry2 = make_evidence_frame(downscale_for_inference(raw_small, 960), raw_small, "bgr", 1.0, 1)
    small2[:, :, :] = 0
    assert np.any(entry2.payload != 0)


def test_roi_crop_copy_does_not_mutate_ring_original():
    raw = make_frame(5)
    entry = make_evidence_frame(downscale_for_inference(raw, 960), raw, "bgr", 1.0, 1)
    original = entry.payload.copy()
    roi = entry.payload[100:200, 100:200].copy()  # derived view MUST copy
    roi[:, :, :] = 0
    assert np.array_equal(entry.payload, original)


def test_jpeg90_roundtrip_decodes_close_and_smaller():
    frame = make_frame(6)
    entry = make_evidence_frame(frame, None, "jpeg90", 1.0, 1, jpeg_quality=90)
    assert entry.fmt == "jpeg90"
    assert entry.nbytes < frame.nbytes
    decoded = decode_evidence_frame(entry)
    assert decoded.shape == frame.shape
    mse = float(np.mean((decoded.astype(np.float64) - frame.astype(np.float64)) ** 2))
    psnr = 10 * np.log10(255.0 ** 2 / max(mse, 1e-9))
    assert psnr > 30.0, f"jpeg90 PSNR too low: {psnr:.1f} dB"


def test_nv12_roundtrip_shape_and_subsampling():
    frame = make_frame(7)
    entry = make_evidence_frame(frame, None, "nv12", 1.0, 1)
    assert entry.nbytes == frame.nbytes // 2  # 4:2:0 half of BGR
    decoded = decode_evidence_frame(entry)
    assert decoded.shape == frame.shape
    assert not np.array_equal(decoded, frame)  # lossy is explicit, not hidden


def test_materialize_returns_writer_tuples_and_fits_mixed_sizes():
    big = make_frame(8, height=540, width=960)
    small = make_frame(9, height=360, width=640)
    entries = [
        make_evidence_frame(big, None, "bgr", 1.0, 1),
        make_evidence_frame(small, None, "bgr", 1.1, 2),
    ]
    samples, adjusted = materialize_evidence_samples(entries)
    assert adjusted == 1
    assert all(isinstance(s, tuple) and len(s) == 2 for s in samples)
    assert all(s[1].shape == (540, 960, 3) for s in samples)
    # fitting NEVER upscales content: the small frame is letterboxed, so its
    # content occupies a 640x360 region inside the canvas (border is black).
    padded = samples[1][1]
    top = (540 - 360) // 2
    left = (960 - 640) // 2
    assert np.all(padded[: top or 1, :] == 0)
    content = padded[top : top + 360, left : left + 640]
    assert np.array_equal(content, small)


def test_fit_evidence_frame_identity_when_sizes_match():
    frame = make_frame(10, height=360, width=640)
    fitted, changed = fit_evidence_frame(frame, 640, 360)
    assert fitted is frame and changed is False


def test_fit_evidence_frame_downscales_larger_never_upscales():
    big = make_frame(11, height=540, width=960)
    fitted, changed = fit_evidence_frame(big, 640, 360)
    assert changed and fitted.shape == (360, 640, 3)


def test_decoded_post_queue_preserves_writer_contract():
    inner = queue.Queue(maxsize=8)
    inner.put_nowait(make_evidence_frame(make_frame(12), None, "jpeg90", 2.0, 5))
    inner.put_nowait(None)
    view = DecodedPostQueue(inner, canvas=(960, 540))
    item = view.get(timeout=0.1)
    assert isinstance(item, tuple) and item[0] == 2.0
    assert item[1].shape == (540, 960, 3)
    assert view.get(timeout=0.1) is None  # sentinel passes through untouched


def test_iter_evidence_frames_yields_bgr_arrays():
    entries = [make_evidence_frame(make_frame(i), None, "jpeg90", float(i), i) for i in (13, 14)]
    frames = list(iter_evidence_frames(entries))
    assert len(frames) == 2 and all(f.shape == (540, 960, 3) for f in frames)
