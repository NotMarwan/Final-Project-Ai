"""
inference.py — Violence Detection Inference Script
====================================================
Senior Computer Vision Engineer — Production-Ready

Usage:
    python inference.py --input input_video.mp4 --output output_video.mp4
    python inference.py --input input_video.mp4 --output output_video.mp4 --weights path/to/best_model.pt
    python inference.py --input input_video.mp4 --output output_video.mp4 --threshold 0.6 --show_fps
"""

import argparse
import time
import sys
from collections import deque
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from einops import rearrange


# ──────────────────────────────────────────────────────────────────────────────
# 1. Model Architecture  (must match training exactly)
# ──────────────────────────────────────────────────────────────────────────────

class SlowFastBackbone(nn.Module):
    def __init__(self, pretrained: bool = False):
        super().__init__()
        try:
            self.backbone = torch.hub.load(
                "facebookresearch/pytorchvideo", "slowfast_r50", pretrained=pretrained
            )
            self.backbone.blocks[-1] = nn.Identity()
            self.out_dim = 2304
        except Exception as e:
            print(f"[WARN] pytorchvideo not available ({e}). Falling back to r3d_18.")
            import torchvision.models.video as vm
            m = vm.r3d_18(pretrained=pretrained)
            self.backbone = nn.Sequential(*list(m.children())[:-2])
            self.pool = nn.AdaptiveAvgPool3d((1, 1, 1))
            self.out_dim = 512

    def forward(self, slow: torch.Tensor, fast: torch.Tensor) -> torch.Tensor:
        if hasattr(self, "pool"):
            return self.pool(
                self.backbone(rearrange(fast, "b t c h w -> b c t h w"))
            ).flatten(1)
        return self.backbone([
            rearrange(slow, "b t c h w -> b c t h w"),
            rearrange(fast, "b t c h w -> b c t h w"),
        ]).flatten(1)


class ViolenceDetector(nn.Module):
    def __init__(self, num_classes: int = 2):
        super().__init__()
        self.sf = SlowFastBackbone(pretrained=False)
        dim = self.sf.out_dim
        self.head = nn.Sequential(
            nn.LayerNorm(dim),
            nn.Linear(dim, 512),
            nn.GELU(),
            nn.Dropout(0.4),
            nn.Linear(512, num_classes),
        )

    def forward(self, slow: torch.Tensor, fast: torch.Tensor) -> torch.Tensor:
        return self.head(self.sf(slow, fast))


# ──────────────────────────────────────────────────────────────────────────────
# 2. Preprocessing  (must match training transforms exactly)
# ──────────────────────────────────────────────────────────────────────────────

MEAN = np.array([0.45, 0.45, 0.45], dtype=np.float32)
STD  = np.array([0.225, 0.225, 0.225], dtype=np.float32)
FRAME_SIZE    = 224      # Height & Width expected by the model
WINDOW_SIZE   = 32       # Fast-pathway frame count
SLOW_STRIDE   = 4        # slow = fast[::4]  →  8 frames
VIOLENCE_CLS  = 1        # Class index for "Violence"


def preprocess_frames(frames: list[np.ndarray]) -> tuple[torch.Tensor, torch.Tensor]:
    """
    Convert a list of 32 BGR OpenCV frames to (slow, fast) tensors.

    Returns
    -------
    slow : Tensor  [1, 8,  3, 224, 224]
    fast : Tensor  [1, 32, 3, 224, 224]
    """
    processed = []
    for frame in frames:
        # Resize → RGB → float32 in [0, 1] → normalize
        img = cv2.resize(frame, (FRAME_SIZE, FRAME_SIZE), interpolation=cv2.INTER_LINEAR)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        img = (img - MEAN) / STD                       # shape: (H, W, 3)
        processed.append(img)

    fast_np = np.stack(processed, axis=0)              # (32, H, W, 3)
    slow_np = fast_np[::SLOW_STRIDE]                   # ( 8, H, W, 3)

    # numpy (T, H, W, C) → torch (1, T, C, H, W)
    to_tensor = lambda x: torch.from_numpy(
        x.transpose(0, 3, 1, 2)                        # (T, C, H, W)
    ).unsqueeze(0)                                      # (1, T, C, H, W)

    return to_tensor(slow_np), to_tensor(fast_np)


# ──────────────────────────────────────────────────────────────────────────────
# 3. Overlay Utilities
# ──────────────────────────────────────────────────────────────────────────────

# Colors in BGR
RED    = (0,   0,   255)
GREEN  = (0,   255, 0)
WHITE  = (255, 255, 255)
BLACK  = (0,   0,   0)
YELLOW = (0,   210, 255)


def draw_violence_overlay(frame: np.ndarray, confidence: float) -> np.ndarray:
    """Draw a semi-transparent red banner + confidence badge on a frame."""
    h, w = frame.shape[:2]
    overlay = frame.copy()

    # ── Red top banner ────────────────────────────────────────────────────────
    banner_h = max(60, h // 10)
    cv2.rectangle(overlay, (0, 0), (w, banner_h), (0, 0, 180), -1)
    cv2.addWeighted(overlay, 0.65, frame, 0.35, 0, frame)  # blend into frame

    # ── Warning text ─────────────────────────────────────────────────────────
    label    = "⚠  VIOLENCE DETECTED"
    font     = cv2.FONT_HERSHEY_DUPLEX
    scale    = max(0.7, w / 900)
    thickness = max(1, int(scale * 2))
    (tw, th), baseline = cv2.getTextSize(label, font, scale, thickness)
    tx = (w - tw) // 2
    ty = banner_h // 2 + th // 2
    # Shadow
    cv2.putText(frame, label, (tx + 2, ty + 2), font, scale, BLACK, thickness + 1, cv2.LINE_AA)
    cv2.putText(frame, label, (tx, ty),          font, scale, WHITE, thickness,     cv2.LINE_AA)

    # ── Confidence badge (bottom-right) ───────────────────────────────────────
    badge_label = f"Confidence: {confidence:.1%}"
    bscale      = max(0.55, w / 1100)
    bthickness  = max(1, int(bscale * 2))
    (bw, bh), _ = cv2.getTextSize(badge_label, font, bscale, bthickness)
    pad  = 8
    bx   = w - bw - pad * 2 - 6
    by   = h - pad * 2 - 6
    cv2.rectangle(frame, (bx - pad, by - bh - pad), (bx + bw + pad, by + pad), BLACK, -1)
    cv2.rectangle(frame, (bx - pad, by - bh - pad), (bx + bw + pad, by + pad), RED, 2)
    cv2.putText(frame, badge_label, (bx, by), font, bscale, YELLOW, bthickness, cv2.LINE_AA)

    # ── Red border around the frame ───────────────────────────────────────────
    border = max(3, h // 80)
    cv2.rectangle(frame, (0, 0), (w - 1, h - 1), RED, border)

    return frame


def draw_safe_overlay(frame: np.ndarray, confidence: float) -> np.ndarray:
    """Draw a subtle green badge when no violence is detected."""
    h, w    = frame.shape[:2]
    label   = f"Safe  {confidence:.1%}"
    font    = cv2.FONT_HERSHEY_DUPLEX
    scale   = max(0.55, w / 1100)
    thick   = max(1, int(scale * 2))
    (tw, th), _ = cv2.getTextSize(label, font, scale, thick)
    pad = 8
    x, y = 10, th + pad * 2
    cv2.rectangle(frame, (x - pad, y - th - pad), (x + tw + pad, y + pad), BLACK, -1)
    cv2.rectangle(frame, (x - pad, y - th - pad), (x + tw + pad, y + pad), GREEN, 2)
    cv2.putText(frame, label, (x, y), font, scale, GREEN, thick, cv2.LINE_AA)
    return frame


def draw_fps_counter(frame: np.ndarray, fps: float) -> np.ndarray:
    label = f"FPS: {fps:.1f}"
    cv2.putText(frame, label, (10, frame.shape[0] - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, YELLOW, 1, cv2.LINE_AA)
    return frame


# ──────────────────────────────────────────────────────────────────────────────
# 4. Core Inference Pipeline
# ──────────────────────────────────────────────────────────────────────────────

class ViolenceInferencePipeline:
    """
    Rolling-window inference pipeline for real-time / batch video processing.

    The window slides by `stride` frames after each prediction.  Frames in the
    overlap region reuse the same prediction label so that annotations are
    continuous and smooth.
    """

    def __init__(
        self,
        weights_path: str,
        device: torch.device,
        threshold: float = 0.5,
        stride: int = 16,
    ):
        self.device    = device
        self.threshold = threshold
        self.stride    = stride

        # ── Load model ────────────────────────────────────────────────────────
        print(f"[INFO] Loading model weights from: {weights_path}")
        self.model = ViolenceDetector(num_classes=2).to(device)

        state = torch.load(weights_path, map_location=device)
        # Support both raw state-dicts and checkpoint dicts
        if isinstance(state, dict) and "model_state_dict" in state:
            state = state["model_state_dict"]
        elif isinstance(state, dict) and "state_dict" in state:
            state = state["state_dict"]

        self.model.load_state_dict(state)
        self.model.eval()
        print(f"[INFO] Model loaded successfully on {device}.")

        # ── Rolling buffer ────────────────────────────────────────────────────
        self._buffer: deque[np.ndarray] = deque(maxlen=WINDOW_SIZE)
        self._last_label: int   = 0       # 0 = Safe, 1 = Violence
        self._last_conf: float  = 0.0
        self._frames_since_pred = 0

    def reset(self) -> None:
        self._buffer.clear()
        self._last_label       = 0
        self._last_conf        = 0.0
        self._frames_since_pred = 0

    @torch.inference_mode()
    def _predict_window(self) -> tuple[int, float]:
        """Run one forward pass on the current buffer contents."""
        frames = list(self._buffer)

        # If buffer not full yet, pad by repeating the last frame
        while len(frames) < WINDOW_SIZE:
            frames.append(frames[-1] if frames else np.zeros(
                (FRAME_SIZE, FRAME_SIZE, 3), dtype=np.uint8))

        slow, fast = preprocess_frames(frames)
        slow = slow.to(self.device, non_blocking=True)
        fast = fast.to(self.device, non_blocking=True)

        logits = self.model(slow, fast)                  # (1, 2)
        probs  = F.softmax(logits, dim=-1)[0]            # (2,)
        violence_prob = probs[VIOLENCE_CLS].item()
        label = int(violence_prob >= self.threshold)
        return label, violence_prob

    def process_frame(self, frame: np.ndarray) -> np.ndarray:
        """
        Push one BGR frame through the pipeline and return the annotated frame.
        A new inference is triggered every `stride` frames once the buffer is full.
        """
        self._buffer.append(frame)
        self._frames_since_pred += 1

        # Trigger a new prediction every `stride` frames (or on first full window)
        if len(self._buffer) == WINDOW_SIZE and self._frames_since_pred >= self.stride:
            self._last_label, self._last_conf = self._predict_window()
            self._frames_since_pred = 0

        # Apply annotation based on the most-recent prediction
        annotated = frame.copy()
        if self._last_label == VIOLENCE_CLS:
            annotated = draw_violence_overlay(annotated, self._last_conf)
        else:
            safe_conf = 1.0 - self._last_conf
            annotated = draw_safe_overlay(annotated, safe_conf)

        return annotated


# ──────────────────────────────────────────────────────────────────────────────
# 5. Video I/O
# ──────────────────────────────────────────────────────────────────────────────

def get_video_writer(
    output_path: str,
    fps: float,
    width: int,
    height: int,
) -> cv2.VideoWriter:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    if not writer.isOpened():
        raise IOError(f"Could not open VideoWriter for path: {output_path}")
    return writer


def run_inference(
    input_path: str,
    output_path: str,
    weights_path: str,
    threshold: float = 0.5,
    stride: int = 16,
    show_fps: bool = False,
) -> None:
    # ── Device ────────────────────────────────────────────────────────────────
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type == "cuda":
        gpu_name = torch.cuda.get_device_name(0)
        print(f"[INFO] CUDA available — using GPU: {gpu_name}")
    else:
        print("[WARN] CUDA not available — running on CPU (will be slow).")

    # ── Validate paths ────────────────────────────────────────────────────────
    if not Path(input_path).exists():
        sys.exit(f"[ERROR] Input video not found: {input_path}")
    if not Path(weights_path).exists():
        sys.exit(f"[ERROR] Weights file not found: {weights_path}")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # ── Open video ────────────────────────────────────────────────────────────
    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        sys.exit(f"[ERROR] Cannot open video: {input_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    src_fps      = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width        = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height       = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    # فرض دقة عالية لتوضيح النص
    if width < 1280:
        scale = 1280 / width
        width = int(width * scale)
        height = int(height * scale)

    print(f"[INFO] Input  : {input_path}")
    print(f"[INFO] Output : {output_path}")
    print(f"[INFO] Video  : {width}×{height} @ {src_fps:.2f} FPS  |  {total_frames} frames")
    print(f"[INFO] Config : threshold={threshold}  stride={stride}  window={WINDOW_SIZE}")

    # ── Pipeline & writer ─────────────────────────────────────────────────────
    pipeline = ViolenceInferencePipeline(
        weights_path=weights_path,
        device=device,
        threshold=threshold,
        stride=stride,
    )
    writer = get_video_writer(output_path, src_fps, width, height)

    # ── Main loop ─────────────────────────────────────────────────────────────
    processed    = 0
    violence_cnt = 0
    t_loop_start = time.perf_counter()
    fps_timer    = time.perf_counter()
    fps_display  = 0.0

    print("[INFO] Starting inference … (press Ctrl+C to abort)\n")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            # تكبير الإطار بالخوارزمية التكعيبية قبل المعالجة والرسم
            if frame.shape[1] < 1280:
                frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_CUBIC)

            annotated = pipeline.process_frame(frame)

            if show_fps:
                now = time.perf_counter()
                fps_display = 1.0 / max(now - fps_timer, 1e-6)
                fps_timer   = now
                annotated   = draw_fps_counter(annotated, fps_display)

            writer.write(annotated)
            processed += 1

            if pipeline._last_label == VIOLENCE_CLS:
                violence_cnt += 1

            # ── Progress bar ─────────────────────────────────────────────────
            if total_frames > 0 and processed % 30 == 0:
                pct     = processed / total_frames * 100
                elapsed = time.perf_counter() - t_loop_start
                eta     = (elapsed / processed) * (total_frames - processed)
                bar_len = 30
                filled  = int(bar_len * processed // total_frames)
                bar     = "█" * filled + "░" * (bar_len - filled)
                print(
                    f"\r  [{bar}] {pct:5.1f}%  "
                    f"frame {processed}/{total_frames}  "
                    f"ETA {eta:.0f}s   ",
                    end="",
                    flush=True,
                )

    except KeyboardInterrupt:
        print("\n[WARN] Inference interrupted by user.")

    finally:
        cap.release()
        writer.release()

    # ── Summary ───────────────────────────────────────────────────────────────
    total_time    = time.perf_counter() - t_loop_start
    avg_fps       = processed / max(total_time, 1e-6)
    violence_pct  = violence_cnt / max(processed, 1) * 100

    print(f"\n\n{'─'*55}")
    print(f"  ✅  Inference complete")
    print(f"{'─'*55}")
    print(f"  Frames processed  : {processed}")
    print(f"  Violence frames   : {violence_cnt}  ({violence_pct:.1f}%)")
    print(f"  Total time        : {total_time:.2f}s")
    print(f"  Average FPS       : {avg_fps:.1f}")
    print(f"  Output saved to   : {output_path}")
    print(f"{'─'*55}\n")


# ──────────────────────────────────────────────────────────────────────────────
# 6. CLI Entry Point
# ──────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Violence Detection Inference — SlowFast Model",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input",     required=True,          help="Path to input video (.mp4)")
    parser.add_argument("--output",    required=True,          help="Path for annotated output video (.mp4)")
    parser.add_argument("--weights",   default="best_model.pt",help="Path to model weights (.pt)")
    parser.add_argument("--threshold", type=float, default=0.5,help="Violence probability threshold [0–1]")
    parser.add_argument("--stride",    type=int,   default=16, help="Frames between predictions (lower = more frequent)")
    parser.add_argument("--show_fps",  action="store_true",    help="Overlay realtime FPS counter on output frames")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_inference(
        input_path   = args.input,
        output_path  = args.output,
        weights_path = args.weights,
        threshold    = args.threshold,
        stride       = args.stride,
        show_fps     = args.show_fps,
    )
