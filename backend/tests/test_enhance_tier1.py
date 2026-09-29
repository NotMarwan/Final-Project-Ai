"""WT-23 tier-1 tests: Real-ESRGAN wiring, harness gating, refusal accounting.

The real weights are untracked (`assets/`), so model tests skip with a reason
when absent; the gate/refusal logic is exercised with a stub enhancer so it is
tested everywhere.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

import enhance as E
import enhance_harness as H
import enhance_tier1 as T1
from evidence import EvidenceLedgerConfig

ASSETS = Path(__file__).resolve().parents[2] / "assets"
WEIGHTS = ASSETS / "RealESRGAN_x4plus.pth"
REALESRGAN_SHA256 = "4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1"


class StubEnhancer:
    """Deterministic stand-in with the same surface as ``RealEsrganEnhancer``."""

    def __init__(self, transform, scale: int = 4, name: str = "stub-sr"):
        self._transform = transform
        self.scale = scale
        self._name = name

    @property
    def provenance(self) -> dict:
        return {"name": self._name, "version": "test", "weightsSha256": "9" * 64, "license": "test-only"}

    def model_block(self) -> dict:
        provenance = self.provenance
        return {
            "name": provenance["name"],
            "version": provenance["version"],
            "weightsSha256": provenance["weightsSha256"],
            "license": provenance["license"],
        }

    def enhance(self, bgr: np.ndarray) -> T1.Tier1Result:
        image = self._transform(bgr)
        return T1.Tier1Result(
            image=image,
            device="stub",
            inference_ms=1.0,
            input_shape=(bgr.shape[0], bgr.shape[1], 3),
            output_shape=(image.shape[0], image.shape[1], 3),
            scale=self.scale,
        )


def permissive_bounds() -> H.HarnessBounds:
    """Bounds that only require the two always-available metrics."""
    return H.HarnessBounds(
        min_psnr_db=-1.0,
        min_ssim=-1.0,
        max_lpips=10.0,
        min_identity_similarity=-1.0,
        require_lpips=False,
        require_identity_when_face=False,
        require_face_preserved=False,
    )


def fixture_crop() -> np.ndarray:
    fixture = ASSETS / "fixtures" / "face_pd_nasa.jpg"
    if fixture.exists():
        image = cv2.imread(str(fixture))
        if image is not None:
            return cv2.resize(image, (160, 160))
    rng = np.random.default_rng(11)
    return (rng.random((64, 64, 3)) * 255).astype(np.uint8)


def service_in(tmp_path: Path) -> E.EnhancementService:
    ledger = E.DerivativeLedger(EvidenceLedgerConfig(tmp_path / "chain.jsonl"))
    ledger.append_entry(
        alert={"id": "alert-t1", "cameraId": "cam-1", "confidence": 80, "severity": "high"},
        clip_path=None,
        snapshot_path=None,
        report_path=None,
        report_text="summary",
    )
    original = tmp_path / "frame.png"
    cv2.imwrite(str(original), fixture_crop())
    service = E.EnhancementService(ledger, evidence_dir=tmp_path / "evidence_clips")
    service.register_parent(
        alert_id="alert-t1",
        camera_id="cam-1",
        parent_path=str(original),
        parent_sha256=E.sha256_file_bytes(original),
        parent_hash_basis=E.HASH_BASIS_FILE,
        parent_hash_format=E.raw_pixel_hash_format(fixture_crop()),
    )
    return service


def crop_ref() -> E.CropRef:
    frame = fixture_crop()
    return E.CropRef(
        alert_id="alert-t1",
        camera_id="cam-1",
        subject_kind="face",
        bbox_xyxy=(0, 0, frame.shape[1], frame.shape[0]),
        face_index=0,
        crop_id="cam-1:12:face:0",
        frame_sequence=12,
    )


def test_reference_selection_prefers_fewest_failures_then_lowest_lpips():
    reports = {
        "nearest": {"failedBounds": ["lpips>0.35"], "lpips": 0.9, "ssim": 0.8},
        "cubic": {"failedBounds": [], "lpips": 0.30, "ssim": 0.85},
        "lanczos": {"failedBounds": [], "lpips": 0.28, "ssim": 0.84},
    }
    name, chosen = T1.Tier1Pipeline._select_reference(reports, permissive_bounds())
    assert name == "lanczos" and chosen["lpips"] == 0.28
    reports["lanczos"]["lpips"] = None
    name, _ = T1.Tier1Pipeline._select_reference(reports, permissive_bounds())
    assert name == "cubic"


def test_tier1_pipeline_refuses_a_candidate_outside_bounds_and_publishes_nothing(tmp_path):
    def destroy(crop: np.ndarray) -> np.ndarray:
        upscaled = cv2.resize(crop, (crop.shape[1] * 4, crop.shape[0] * 4), interpolation=cv2.INTER_NEAREST)
        return cv2.GaussianBlur(upscaled, (31, 31), 9.0)

    service = service_in(tmp_path)
    pipeline = T1.Tier1Pipeline(StubEnhancer(destroy), service, bounds=H.default_bounds(tier=1))
    with pytest.raises(T1.Tier1RefusedByHarness) as excinfo:
        pipeline.enhance_crop(crop_ref(), fixture_crop())
    assert "failedBounds" in str(excinfo.value) or "refused" in str(excinfo.value)
    assert pipeline.stats == {"attempts": 1, "refused": 1, "published": 0}
    assert service.ledger.derivatives_for_alert("alert-t1") == []
    derivative_dir = tmp_path / "evidence_clips" / "derivatives"
    assert not derivative_dir.exists() or not list(derivative_dir.glob("*.png"))


def test_tier1_pipeline_publishes_a_labeled_learned_derivative_after_measurement(tmp_path):
    def sharpen(crop: np.ndarray) -> np.ndarray:
        return cv2.resize(crop, (crop.shape[1] * 4, crop.shape[0] * 4), interpolation=cv2.INTER_LANCZOS4)

    service = service_in(tmp_path)
    pipeline = T1.Tier1Pipeline(StubEnhancer(sharpen), service, bounds=permissive_bounds())
    record = pipeline.enhance_crop(crop_ref(), fixture_crop())
    assert pipeline.stats == {"attempts": 1, "refused": 0, "published": 1}
    assert record["tier"] == 1 and record["derivationBasis"] == "learned"
    assert record["model"] == {
        "name": "stub-sr",
        "version": "test",
        "weightsSha256": "9" * 64,
        "license": "test-only",
    }
    assert record["operations"][0]["name"] == "real_esrgan_x4"
    used = record["operations"][0]["params"]["comparisonBaseline"]
    assert used.startswith(("nearest", "cubic", "lanczos"))
    assert set(record["harness"]["comparisonBaselines"]) == {"nearest", "cubic", "lanczos"}
    assert record["label"] == E.DERIVATIVE_LABEL_ENHANCED and record["isEnhanced"] is True
    assert record["uiContract"]["originalFirst"] is True
    assert record["harness"]["status"] == H.STATUS_MEASURED and record["harness"]["passed"] is True
    assert record["harness"]["comparisonBaselines"].keys() == {"nearest", "cubic", "lanczos"}
    assert record["subjectRef"]["isDerivative"] is True and record["subjectRef"]["derivativeOf"] == "cam-1:12:face:0"
    published = tmp_path / "evidence_clips" / Path(record["derivativePath"]).relative_to("evidence_clips")
    assert published.exists() and record["derivativeSha256"] == E.sha256_file_bytes(published)
    assert E.read_png_text_labels(published.read_bytes())["Label"] == E.DERIVATIVE_LABEL_ENHANCED


def test_tier1_refusal_is_counted_by_the_scheduler_not_raised_into_the_alert_path(tmp_path):
    def destroy(crop: np.ndarray) -> np.ndarray:
        upscaled = cv2.resize(crop, (crop.shape[1] * 4, crop.shape[0] * 4), interpolation=cv2.INTER_NEAREST)
        return (upscaled // 63) * 63

    service = service_in(tmp_path)
    pipeline = T1.Tier1Pipeline(StubEnhancer(destroy), service, bounds=H.default_bounds(tier=1))
    scheduler = E.EnhancementScheduler(pipeline.enhance_crop_job_wrapper if hasattr(pipeline, "enhance_crop_job_wrapper") else _job_handler(pipeline), queue_size=4, poll_interval=0.005)
    scheduler.start()
    try:
        scheduler.enqueue(
            E.EnhancementJob(
                job_id="tier1-refusal",
                alert_id="alert-t1",
                camera_id="cam-1",
                tier=1,
                crop=crop_ref(),
                parent_sha256=E.sha256_file_bytes(tmp_path / "frame.png"),
                parent_path=str(tmp_path / "frame.png"),
                parent_hash_basis=E.HASH_BASIS_FILE,
                parent_frame=fixture_crop(),
            )
        )
        assert scheduler.drain(timeout=5.0)
    finally:
        scheduler.stop()
    assert scheduler.stats.completed == 0 and scheduler.stats.failed == 1
    assert "tier1_refused_by_harness" in (scheduler.stats.last_error or "")


def _job_handler(pipeline: T1.Tier1Pipeline):
    def handler(job: E.EnhancementJob) -> dict:
        return pipeline.enhance_crop(job.crop, job.parent_frame, parent_path=job.parent_path, parent_sha256=job.parent_sha256)

    return handler


@pytest.mark.skipif(not WEIGHTS.exists(), reason="untracked assets/RealESRGAN_x4plus.pth missing")
def test_realesrgan_loads_the_official_weights_strictly_and_reports_provenance():
    enhancer = T1.RealEsrganEnhancer(WEIGHTS, device="cpu", max_input_side=256)
    provenance = enhancer.provenance
    assert provenance["weightsSha256"] == REALESRGAN_SHA256
    assert provenance["license"].startswith("BSD-3-Clause")
    assert provenance["parameters"] == {"numFeat": 64, "numBlock": 23, "numGrowCh": 32, "scale": 4}
    assert enhancer.model_block()["name"] == "real-esrgan"


@pytest.mark.skipif(not WEIGHTS.exists(), reason="untracked assets/RealESRGAN_x4plus.pth missing")
def test_realesrgan_output_is_scaled_uint8_and_deterministic():
    enhancer = T1.RealEsrganEnhancer(WEIGHTS, device="cpu", max_input_side=256)
    crop = fixture_crop()[:64, :64]
    first = enhancer.enhance(crop)
    second = enhancer.enhance(crop)
    assert first.image.shape[:2] == (64 * 4, 64 * 4)
    assert first.image.dtype == np.uint8
    assert first.image.tobytes() == second.image.tobytes()
    assert first.scale == 4 and first.inference_ms > 0


@pytest.mark.skipif(not WEIGHTS.exists(), reason="untracked assets/RealESRGAN_x4plus.pth missing")
def test_realesrgan_refuses_an_oversized_input_instead_of_running_unbounded():
    enhancer = T1.RealEsrganEnhancer(WEIGHTS, device="cpu", max_input_side=64)
    with pytest.raises(T1.Tier1InputTooLarge):
        enhancer.enhance(fixture_crop()[:128, :128])


def test_tier1_backend_reports_absence_honestly(tmp_path):
    with pytest.raises(T1.Tier1BackendUnavailable):
        T1.RealEsrganEnhancer(tmp_path / "missing.pth", device="cpu")
