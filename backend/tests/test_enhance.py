"""WT-23 tests: tier-0 enhancement, SC-8 derivative records, harness, async schedule.

Scoped to the enhancement modules; no network, no camera, deterministic. Tests
that need the untracked ``assets/`` weights skip with an explicit reason so the
suite still reflects the truth when the weights are absent.
"""

from __future__ import annotations

import hashlib
import json
import math
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

import enhance as E
import enhance_harness as H
from evidence import EvidenceIntegrityError, EvidenceLedger, EvidenceLedgerConfig

ASSETS = Path(__file__).resolve().parents[2] / "assets"
YUNET = ASSETS / "face_detection_yunet_2023mar.onnx"
SFACE = ASSETS / "face_recognition_sface_2021dec.onnx"
FIXTURE = ASSETS / "fixtures" / "face_pd_nasa.jpg"


def gradient_frame(height: int = 96, width: int = 128, seed: int = 3) -> np.ndarray:
    columns = np.linspace(20, 235, width, dtype=np.float32)[None, :]
    rows = np.linspace(0, 40, height, dtype=np.float32)[:, None]
    blue = (columns + rows).clip(0, 255)
    green = (columns * 0.6 + 60 + rows * 0.2).clip(0, 255)
    red = (220 - columns * 0.5 + rows * 0.3).clip(0, 255)
    frame = np.dstack([blue, green, red]).astype(np.uint8)
    rng = np.random.default_rng(seed)
    return np.clip(frame.astype(np.int16) + rng.integers(-4, 5, frame.shape), 0, 255).astype(np.uint8)


def alert_receipt(ledger: EvidenceLedger, alert_id: str) -> dict:
    return ledger.append_entry(
        alert={"id": alert_id, "cameraId": "cam-1", "confidence": 90, "severity": "high"},
        clip_path=None,
        snapshot_path=None,
        report_path=None,
        report_text="Local factual summary",
    )


def parent_frame(tmp_path: Path) -> tuple[Path, str, str]:
    path = tmp_path / "original_frame.png"
    cv2.imwrite(str(path), gradient_frame())
    return path, E.sha256_file_bytes(path), E.HASH_BASIS_FILE


def derivative_ops() -> E.Tier0Ops:
    return E.Tier0Ops(clahe=True, gamma=1.2)


def make_record(tmp_path: Path, *, alert_id: str, derivative_id: str, parent_sha: str, tier: int = 0, **overrides) -> dict:
    output = tmp_path / f"{derivative_id}.png"
    cv2.imwrite(str(output), gradient_frame())
    operations = [{"name": "crop", "params": {"bboxXyxy": [0, 0, 128, 96]}}]
    if tier == 0:
        operations.append({"name": "gamma", "params": {"gamma": 1.2}})
    payload = dict(
        derivative_id=derivative_id,
        alert_id=alert_id,
        camera_id="cam-1",
        parent_kind="frame",
        parent_path=str(tmp_path / "original_frame.png"),
        parent_sha256=parent_sha,
        parent_hash_basis=E.HASH_BASIS_FILE,
        parent_captured_at=1234.5,
        parent_sample_timestamp=12.5,
        subject_ref={"kind": "person", "trackId": "cam-1::7", "bboxXyxy": [1, 2, 30, 40]},
        derivative_path=str(output),
        derivative_sha256=E.sha256_file_bytes(output),
        operations=operations,
        tier=tier,
        model={"name": "real-esrgan", "version": "x4plus", "weightsSha256": "a" * 64, "license": "BSD-3-Clause"}
        if tier == 1
        else None,
    )
    payload.update(overrides)
    return E.build_derivative_record(**payload)


# ---------------------------------------------------------------------------
# Tier-0 operations
# ---------------------------------------------------------------------------


def test_tier0_is_byte_deterministic_for_same_input_and_params():
    frame = gradient_frame()
    first, operations = E.apply_tier0(frame, derivative_ops(), (10, 10, 110, 80))
    second, _ = E.apply_tier0(frame, derivative_ops(), (10, 10, 110, 80))
    assert E.sha256_pixels(first) == E.sha256_pixels(second)
    assert first.tobytes() == second.tobytes()
    assert [entry["name"] for entry in operations] == ["crop", "clahe", "gamma"]


def test_crop_only_is_not_labelled_enhanced():
    frame = gradient_frame()
    _, operations = E.apply_tier0(frame, E.Tier0Ops(), (0, 0, 64, 64))
    assert E.operations_are_enhancing(operations) is False
    assert E.operations_are_enhancing(operations + [{"name": "gamma", "params": {}}]) is True


def test_gamma_uses_a_pointwise_monotone_lut():
    frame = gradient_frame(8, 8)
    output, record = E.apply_gamma(frame, 1.4)
    assert record["params"]["gamma"] == 1.4
    # A LUT cannot create new values: the output value set is a subset of the LUT.
    lut = np.array([((index / 255.0) ** (1 / 1.4)) * 255.0 for index in range(256)], dtype=np.uint8)
    assert set(np.unique(output)).issubset(set(np.unique(lut)))
    assert lut[0] == 0 and lut[255] == 255


def test_clahe_denoise_and_stretch_record_their_parameters():
    frame = gradient_frame()
    _, clahe = E.apply_clahe(frame, 2.5, (4, 4))
    _, gamma = E.apply_gamma(frame, 0.9)
    _, denoise = E.apply_denoise_lite(frame, 4.0, 7, 21)
    _, stretch = E.apply_contrast_stretch(frame)
    assert clahe["params"] == {"space": "LAB-L", "clipLimit": 2.5, "tileGridSize": [4, 4]}
    assert gamma["params"] == {"gamma": 0.9, "lutEntries": 256}
    assert denoise["params"]["algorithm"] == "fastNlMeansDenoisingColored"
    assert stretch["params"]["applied"] is True


def test_crop_requires_a_box_and_clamps_out_of_range_coordinates():
    frame = gradient_frame(40, 50)
    with pytest.raises(E.EnhancementError):
        E.apply_tier0(frame, E.Tier0Ops())
    cropped, record = E.crop_frame(frame, (-20, -20, 500, 500))
    assert cropped.shape[:2] == (40, 50)
    assert record["params"]["bboxXyxy"] == [0, 0, 50, 40]
    with pytest.raises(E.EnhancementError):
        E.crop_frame(frame, (10, 10, 10, 30))


def test_raw_pixel_hash_layout_is_the_shared_wire_format():
    frame = gradient_frame(48, 64)
    digest = E.sha256_pixels(frame)
    assert digest == hashlib.sha256(np.ascontiguousarray(frame).tobytes()).hexdigest()
    assert E.raw_pixel_hash_format(frame) == "raw-bgr-48x64x3-uint8"


# ---------------------------------------------------------------------------
# Labeling
# ---------------------------------------------------------------------------


def test_png_labels_survive_round_trip_and_the_file_still_decodes():
    frame = gradient_frame(32, 32)
    labels = E.derivative_labels(is_enhanced=True)
    labels["DerivativeId"] = "deriv-alert-1-001"
    payload = E.encode_png_with_labels(frame, labels)
    parsed = E.read_png_text_labels(payload)
    assert parsed["Label"] == E.DERIVATIVE_LABEL_ENHANCED
    assert parsed["Disclaimer"] == E.LABEL_TEXT_ENHANCED
    assert "—" in parsed["Disclaimer"]  # em dash survives (iTXt/UTF-8, not lossy)
    assert parsed["DerivativeId"] == "deriv-alert-1-001"
    decoded = cv2.imdecode(np.frombuffer(payload, np.uint8), cv2.IMREAD_COLOR)
    assert decoded is not None and decoded.shape == frame.shape


def test_ui_contract_fields_always_require_original_first():
    enhanced = E.ui_contract_fields(True)
    plain = E.ui_contract_fields(False)
    assert enhanced == {
        "originalFirst": True,
        "originalRequired": True,
        "badge": E.DERIVATIVE_LABEL_ENHANCED,
        "disclaimer": E.DERIVATIVE_DISCLAIMER,
    }
    assert plain["badge"] == E.DERIVATIVE_LABEL_CROP and "unmodified pixels" in plain["disclaimer"]


# ---------------------------------------------------------------------------
# Derivative records and the SC-8 chain
# ---------------------------------------------------------------------------


def test_derivative_record_carries_every_required_field(tmp_path):
    path, digest, basis = parent_frame(tmp_path)
    record = make_record(tmp_path, alert_id="alert-1", derivative_id="deriv-alert-1-001", parent_sha=digest)
    for key in E.REQUIRED_DERIVATIVE_KEYS:
        assert key in record, key
    assert record["recordType"] == E.DERIVATIVE_RECORD_TYPE == "enhancement-derivative"
    assert record["label"] == E.DERIVATIVE_LABEL_ENHANCED and record["isEnhanced"] is True
    assert record["parentHashBasis"] == basis
    assert record["parentCapturedAt"] == 1234.5 and record["parentSampleTimestamp"] == 12.5
    assert record["subjectRef"]["trackId"] == "cam-1::7"
    assert record["labelLocations"] == ["image_metadata", "ledger_record", "ui_contract"]
    assert record["libraryVersions"]["opencv"] == cv2.__version__


@pytest.mark.parametrize("placeholder", ["N/A", "", None, "unknown", "0", "z" * 64])
def test_placeholder_parent_hashes_are_refused(tmp_path, placeholder):
    path, digest, _ = parent_frame(tmp_path)
    with pytest.raises((E.DerivativeParentUnhashed, E.DerivativeRecordInvalid)):
        make_record(tmp_path, alert_id="alert-1", derivative_id="deriv-1", parent_sha=placeholder)


def test_missing_parent_asset_is_refused_not_hashed_as_placeholder(tmp_path):
    with pytest.raises(E.DerivativeParentMissing):
        E.sha256_file_bytes(tmp_path / "not-here.png")
    assert E.is_placeholder_hash("N/A") and E.is_placeholder_hash(None)
    assert not E.is_placeholder_hash("b" * 64)


def test_derivative_record_rejects_tier1_without_model_provenance(tmp_path):
    path, digest, _ = parent_frame(tmp_path)
    with pytest.raises(E.DerivativeRecordInvalid):
        make_record(
            tmp_path,
            alert_id="alert-1",
            derivative_id="deriv-1",
            parent_sha=digest,
            tier=1,
            model={"name": None, "weightsSha256": None},
        )


def test_validate_rejects_a_record_without_original_first_ui_contract(tmp_path):
    path, digest, _ = parent_frame(tmp_path)
    record = make_record(tmp_path, alert_id="alert-1", derivative_id="deriv-1", parent_sha=digest)
    record["uiContract"] = {"originalFirst": False}
    with pytest.raises(E.DerivativeRecordInvalid):
        E.validate_derivative_record(record)


def test_derivative_ledger_chains_multiple_records_per_alert(tmp_path):
    ledger = E.DerivativeLedger(EvidenceLedgerConfig(tmp_path / "chain.jsonl"))
    alert_receipt(ledger, "alert-a")
    _, digest, _ = parent_frame(tmp_path)
    first = ledger.append_derivative(make_record(tmp_path, alert_id="alert-a", derivative_id="deriv-alert-a-001", parent_sha=digest))
    second = ledger.append_derivative(make_record(tmp_path, alert_id="alert-a", derivative_id="deriv-alert-a-002", parent_sha=digest))
    assert first["prevHash"] != second["prevHash"]
    assert second["prevHash"] == first["currentHash"]
    records = E.verify_derivative_chain(ledger.config.path)
    assert len(records) == 3
    assert [record.get("derivativeId") for record in records[1:]] == ["deriv-alert-a-001", "deriv-alert-a-002"]
    assert len(ledger.derivatives_for_alert("alert-a")) == 2


def test_derivative_append_requires_an_existing_alert_receipt(tmp_path):
    ledger = E.DerivativeLedger(EvidenceLedgerConfig(tmp_path / "chain.jsonl"))
    _, digest, _ = parent_frame(tmp_path)
    with pytest.raises(E.DerivativeOrderingError):
        ledger.append_derivative(make_record(tmp_path, alert_id="alert-x", derivative_id="deriv-1", parent_sha=digest))
    assert not ledger.config.path.exists() or ledger.config.path.read_text(encoding="utf-8") == ""


def test_derivative_append_is_idempotent_on_derivative_id(tmp_path):
    ledger = E.DerivativeLedger(EvidenceLedgerConfig(tmp_path / "chain.jsonl"))
    alert_receipt(ledger, "alert-a")
    _, digest, _ = parent_frame(tmp_path)
    record = make_record(tmp_path, alert_id="alert-a", derivative_id="deriv-alert-a-001", parent_sha=digest)
    first = ledger.append_derivative(record)
    replay = ledger.append_derivative(dict(record))
    assert first == replay
    assert len(ledger._read_records()) == 2


def test_idempotent_replay_from_a_second_ledger_instance_shares_the_chain(tmp_path):
    path = tmp_path / "chain.jsonl"
    writer = E.DerivativeLedger(EvidenceLedgerConfig(path))
    alert_receipt(writer, "alert-a")
    _, digest, _ = parent_frame(tmp_path)
    record = make_record(tmp_path, alert_id="alert-a", derivative_id="deriv-alert-a-001", parent_sha=digest)
    writer.append_derivative(record)
    other = E.DerivativeLedger(EvidenceLedgerConfig(path))
    assert other.append_derivative(dict(record))["currentHash"] == writer.get_derivative("deriv-alert-a-001")["currentHash"]
    assert len(E.verify_derivative_chain(path)) == 2


def test_tampered_chain_blocks_further_derivative_appends(tmp_path):
    path = tmp_path / "chain.jsonl"
    ledger = E.DerivativeLedger(EvidenceLedgerConfig(path))
    alert_receipt(ledger, "alert-a")
    _, digest, _ = parent_frame(tmp_path)
    ledger.append_derivative(make_record(tmp_path, alert_id="alert-a", derivative_id="deriv-alert-a-001", parent_sha=digest))
    lines = path.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[-1])
    tampered["derivativeSha256"] = "c" * 64
    lines[-1] = json.dumps(tampered, sort_keys=True, ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(EvidenceIntegrityError):
        ledger.append_derivative(make_record(tmp_path, alert_id="alert-a", derivative_id="deriv-alert-a-002", parent_sha=digest))


def test_derivative_ids_are_monotone_and_unique(tmp_path):
    ledger = E.DerivativeLedger(EvidenceLedgerConfig(tmp_path / "chain.jsonl"))
    alert_receipt(ledger, "alert-a")
    _, digest, _ = parent_frame(tmp_path)
    ids = E.DerivativeIdAllocator(ledger)
    allocated = [ids.next_id("alert-a") for _ in range(3)]
    assert allocated == ["deriv-alert-a-001", "deriv-alert-a-002", "deriv-alert-a-003"]
    ledger.append_derivative(make_record(tmp_path, alert_id="alert-a", derivative_id=allocated[0], parent_sha=digest))
    assert E.DerivativeIdAllocator(ledger).next_id("alert-a") == "deriv-alert-a-002"


# ---------------------------------------------------------------------------
# Service: file layout, hashing, immutability
# ---------------------------------------------------------------------------


def test_service_publishes_a_labeled_derivative_and_records_its_hash(tmp_path):
    evidence = tmp_path / "evidence_clips"
    ledger = E.DerivativeLedger(EvidenceLedgerConfig(tmp_path / "chain.jsonl"))
    alert_receipt(ledger, "alert-svc")
    original, digest, basis = parent_frame(tmp_path)
    before = E.sha256_file_bytes(original)
    service = E.EnhancementService(ledger, evidence_dir=evidence)
    service.register_parent(
        alert_id="alert-svc",
        camera_id="cam-1",
        parent_path=str(original),
        parent_sha256=digest,
        parent_hash_basis=basis,
        parent_captured_at=99.0,
        parent_sample_timestamp=None,
    )
    crop = E.CropRef(
        alert_id="alert-svc",
        camera_id="cam-1",
        subject_kind="person",
        bbox_xyxy=(8, 8, 88, 72),
        track_id="cam-1::4",
        track_id_raw=4,
        frame_sequence=17,
        hash_format=E.raw_pixel_hash_format(gradient_frame()),
        parent_kind="frame",
    )
    record = service.enhance(crop, gradient_frame(), ops=derivative_ops())
    derivative_file = tmp_path / "evidence_clips" / Path(record["derivativePath"]).relative_to("evidence_clips")
    assert derivative_file.exists()
    assert record["derivativeSha256"] == E.sha256_file_bytes(derivative_file)
    labels = E.read_png_text_labels(derivative_file.read_bytes())
    assert labels["Label"] == E.DERIVATIVE_LABEL_ENHANCED
    assert labels["DerivativeId"] == record["derivativeId"]
    assert labels["ParentSha256"] == digest
    assert record["parentSha256"] == digest and record["parentCapturedAt"] == 99.0
    assert record["subjectRef"]["bboxSpace"] == "source"
    assert record["subjectRef"]["trackIdRaw"] == 4
    assert record["tier"] == 0 and record["derivationBasis"] == "deterministic"
    assert E.sha256_file_bytes(original) == before, "original must be untouched"
    assert E.verify_derivative_chain(ledger.config.path)[-1]["derivativeId"] == record["derivativeId"]


def test_service_refuses_to_write_without_a_registered_parent(tmp_path):
    ledger = E.DerivativeLedger(EvidenceLedgerConfig(tmp_path / "chain.jsonl"))
    alert_receipt(ledger, "alert-none")
    service = E.EnhancementService(ledger, evidence_dir=tmp_path / "evidence_clips")
    crop = E.CropRef(alert_id="alert-none", camera_id=None, subject_kind="face", bbox_xyxy=(0, 0, 16, 16), face_index=0)
    with pytest.raises(E.DerivativeParentMissing):
        service.enhance(crop, gradient_frame(), ops=derivative_ops())


def test_derivative_filename_encodes_subject_and_frame_identity(tmp_path):
    path = E.resolve_derivative_path(tmp_path, "alert-9", "face0", "t12500")
    assert path.name == "alert-9.face0.t12500.enhanced.png"
    assert path.parent.name == "derivatives"
    person = E.CropRef(alert_id="a", camera_id=None, subject_kind="person", bbox_xyxy=(0, 0, 4, 4), track_id="cam::3")
    assert E.subject_tag(person) == "personcam__3"
    raw = E.CropRef(alert_id="a", camera_id=None, subject_kind="person", bbox_xyxy=(0, 0, 4, 4), track_id="cam::3", track_id_raw=3)
    assert E.subject_tag(raw) == "person3"
    frame = E.CropRef(alert_id="a", camera_id=None, subject_kind="frame", bbox_xyxy=(0, 0, 4, 4), frame_sequence=42)
    assert E.frame_tag(frame) == "f42"


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


def test_psnr_matches_the_analytic_value_for_a_constant_shift():
    frame = np.full((16, 16, 3), 100, dtype=np.uint8)
    shifted = np.full((16, 16, 3), 110, dtype=np.uint8)
    assert H.psnr_db(frame, frame) == float("inf")
    assert H.psnr_db(frame, shifted) == pytest.approx(20 * math.log10(255 / 10), rel=1e-9)


def test_ssim_reference_properties():
    frame = gradient_frame(64, 64)
    assert H.ssim(frame, frame) == pytest.approx(1.0, abs=1e-6)
    noisy = np.clip(frame.astype(np.int16) + 40, 0, 255).astype(np.uint8)
    value = H.ssim(frame, noisy)
    assert 0.0 <= value < 1.0
    assert H.ssim(frame, noisy) == pytest.approx(H.ssim(noisy, frame), rel=1e-9)
    with pytest.raises(H.HarnessError):
        H.ssim(frame, frame[:32, :32])


def test_harness_without_backends_reports_unmeasured_metrics_not_fake_numbers():
    frame = gradient_frame(48, 48)
    derivative = E.apply_gamma(frame, 1.2)[0]
    report = H.evaluate(frame, derivative)
    assert report["psnrDb"] is not None and report["ssim"] is not None
    assert report["lpips"] is None and report["lpipsStatus"] == H.STATUS_LPIPS_UNAVAILABLE
    assert report["identitySimilarity"] is None and report["identityStatus"] == H.STATUS_IDENTITY_BACKEND_MISSING
    assert report["utility"]["faceDetectScoreBefore"] is None
    assert report["utilityStatus"] == H.STATUS_NOT_EVALUATED
    assert report["status"] == H.STATUS_MEASURED and report["passed"] is True


def test_tier1_gate_refuses_when_lpips_cannot_be_measured():
    frame = gradient_frame(48, 48)
    derivative = E.apply_gamma(frame, 1.2)[0]
    report = H.evaluate(frame, derivative, bounds=H.default_bounds(tier=1))
    assert report["passed"] is False
    assert "lpips-not-measurable" in report["failedBounds"]
    with pytest.raises(H.HarnessBoundExceeded):
        H.assert_within_bounds(report)


def test_harness_detects_an_identity_erasing_derivative():
    # High-frequency structure is what blur destroys; a smooth gradient survives it.
    indices = np.indices((64, 64))
    checker = (((indices[0] // 4 + indices[1] // 4) % 2) * 235 + 10).astype(np.uint8)
    frame = np.dstack([checker, np.roll(checker, 3, axis=0), np.roll(checker, 5, axis=1)]).copy()
    blurred = cv2.GaussianBlur(frame, (31, 31), 9.0)
    report = H.evaluate(frame, blurred, bounds=H.HarnessBounds(min_psnr_db=14.0, min_ssim=0.60, max_lpips=0.55))
    assert report["ssim"] < 0.60
    assert report["passed"] is False
    assert any(bound.startswith("ssim<") for bound in report["failedBounds"])


def test_assert_within_bounds_rejects_unmeasured_reports():
    with pytest.raises(H.HarnessBoundExceeded):
        H.assert_within_bounds({"status": H.STATUS_NOT_EVALUATED, "passed": None, "failedBounds": []})


def test_default_op_set_is_the_measured_least_distortion_choice():
    ops = E.default_tier0_ops()
    assert ops.gamma == 1.2
    assert ops.clahe is False and ops.denoise_lite is False and ops.contrast_stretch is False
    assert E.EnhancementJob(
        job_id="j", alert_id="a", camera_id=None, tier=0,
        crop=E.CropRef(alert_id="a", camera_id=None, subject_kind="frame", bbox_xyxy=(0, 0, 4, 4)),
        parent_sha256="a" * 64, parent_path="p.png", parent_hash_basis=E.HASH_BASIS_FILE,
    ).ops == ops


def test_identical_pixels_are_recorded_as_null_not_infinite_and_break_no_chain(tmp_path):
    frame = gradient_frame(32, 32)
    report = H.evaluate(frame, frame.copy())
    assert report["psnrDb"] is None and report["identicalPixels"] is True
    assert any("infinite" in note for note in report["notes"])
    assert json.dumps(report, allow_nan=False)  # the ledger serializes without NaN/inf
    ledger = E.DerivativeLedger(EvidenceLedgerConfig(tmp_path / "chain.jsonl"))
    alert_receipt(ledger, "alert-inf")
    _, digest, _ = parent_frame(tmp_path)
    record = make_record(
        tmp_path,
        alert_id="alert-inf",
        derivative_id="deriv-alert-inf-001",
        parent_sha=digest,
        harness=report,
    )
    written = ledger.append_derivative(record)
    assert written["harness"]["psnrDb"] is None
    assert E.verify_derivative_chain(ledger.config.path)[-1]["derivativeId"] == "deriv-alert-inf-001"


def test_derivative_ledger_from_settings_uses_the_same_ledger_path(tmp_path):
    settings = {"storage": {"evidence_ledger_path": "./chain-from-settings.jsonl"}}
    ledger = E.DerivativeLedger.from_settings(settings, tmp_path)
    assert ledger.config.path == tmp_path / "chain-from-settings.jsonl"
    alert_receipt(ledger, "alert-cfg")
    _, digest, _ = parent_frame(tmp_path)
    record = ledger.append_derivative(
        make_record(tmp_path, alert_id="alert-cfg", derivative_id="deriv-alert-cfg-001", parent_sha=digest)
    )
    assert record["alertId"] == "alert-cfg"
    # A second instance built the same way sees the same chain (shared path lock).
    assert E.DerivativeLedger.from_settings(settings, tmp_path).get_derivative("deriv-alert-cfg-001") is not None


def test_service_can_be_constructed_the_way_api_wiring_does(tmp_path):
    service = E.EnhancementService(
        E.DerivativeLedger(EvidenceLedgerConfig(tmp_path / "chain.jsonl")),
        evidence_dir=tmp_path / "evidence_clips",
    )
    scheduler = E.EnhancementScheduler(service.scheduled_handler, queue_size=2)
    scheduler.start()
    scheduler.stop(timeout=1.0)
    assert scheduler.stats.as_dict()["completed"] == 0


@pytest.mark.skipif(not (YUNET.exists() and FIXTURE.exists()), reason="untracked assets/ weights or fixture missing")
def test_yunet_probe_locates_the_fixture_face_and_reports_ied():
    probe = H.FaceProbe(YUNET)
    frame = cv2.imread(str(FIXTURE))
    observation = probe.detect(frame)
    assert observation is not None and observation.score > 0.5
    assert observation.ied_px and observation.ied_px > 20
    assert len(observation.landmarks) == 5
    assert probe.provenance["sha256"] == "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"


@pytest.mark.skipif(not (YUNET.exists() and SFACE.exists() and FIXTURE.exists()), reason="untracked assets/ weights or fixture missing")
def test_identity_similarity_is_one_for_identical_crops_and_drops_for_destruction():
    probe = H.FaceProbe(YUNET)
    identity = H.IdentitySimilarity(SFACE, probe=probe)
    frame = cv2.imread(str(FIXTURE))
    observation = probe.detect(frame)
    x1, y1, x2, y2 = observation.bbox
    crop = frame[max(0, y1 - 30):y2 + 30, max(0, x1 - 30):x2 + 30].copy()
    same, status = identity.measure(crop, crop.copy())
    assert status == H.STATUS_MEASURED and same == pytest.approx(1.0, abs=1e-4)
    destroyed = cv2.GaussianBlur(crop, (31, 31), 9.0)
    scrambled = np.roll(destroyed, shift=17, axis=1)
    other, status = identity.measure(crop, scrambled)
    assert status == H.STATUS_MEASURED and other < same - 0.2


@pytest.mark.skipif(not (YUNET.exists() and FIXTURE.exists()), reason="untracked assets/ weights or fixture missing")
def test_utility_reports_absent_face_honestly():
    probe = H.FaceProbe(YUNET)
    flat = np.full((64, 64, 3), 127, dtype=np.uint8)
    report = H.evaluate(flat, flat, probe=probe)
    assert report["utilityStatus"] == H.STATUS_NO_FACE_ORIGINAL
    assert report["utility"]["faceDetectScoreBefore"] is None
    assert report["identityStatus"] == H.STATUS_IDENTITY_BACKEND_MISSING


# ---------------------------------------------------------------------------
# Async scheduler and GPU budget
# ---------------------------------------------------------------------------


def test_enqueue_is_non_blocking_and_reports_evictions():
    handled: list[str] = []

    def handler(job: E.EnhancementJob) -> None:
        handled.append(job.job_id)

    scheduler = E.EnhancementScheduler(handler, queue_size=3)
    durations = []
    for index in range(50):
        started = time.perf_counter()
        scheduler.enqueue(
            E.EnhancementJob(
                job_id=f"job-{index}",
                alert_id="alert-1",
                camera_id=None,
                tier=0,
                crop=E.CropRef(alert_id="alert-1", camera_id=None, subject_kind="frame", bbox_xyxy=(0, 0, 8, 8)),
                parent_sha256="d" * 64,
                parent_path="frame.png",
                parent_hash_basis=E.HASH_BASIS_FILE,
                not_before=time.monotonic() + 3600,  # keep them queued
            )
        )
        durations.append(time.perf_counter() - started)
    assert max(durations) < 0.01
    assert scheduler.queue_depth() == 3
    assert scheduler.stats.enqueued == 50
    assert scheduler.stats.evicted_oldest == 47
    assert handled == []


def test_worker_counts_failures_without_raising_them():
    attempts = []

    def handler(job: E.EnhancementJob) -> None:
        attempts.append(job.job_id)
        raise E.DerivativeParentMissing("no parent frame in this test")

    scheduler = E.EnhancementScheduler(handler, queue_size=8, poll_interval=0.005)
    scheduler.start()
    try:
        for index in range(3):
            scheduler.enqueue(
                E.EnhancementJob(
                    job_id=f"job-{index}",
                    alert_id="alert-1",
                    camera_id=None,
                    tier=0,
                    crop=E.CropRef(alert_id="alert-1", camera_id=None, subject_kind="frame", bbox_xyxy=(0, 0, 8, 8)),
                    parent_sha256="e" * 64,
                    parent_path="frame.png",
                    parent_hash_basis=E.HASH_BASIS_FILE,
                )
            )
        assert scheduler.drain(timeout=3.0)
    finally:
        scheduler.stop()
    assert len(attempts) == 3
    assert scheduler.stats.completed == 0 and scheduler.stats.failed == 3
    assert "derivative_parent_missing" in (scheduler.stats.last_error or "")


def test_tier1_jobs_yield_while_detection_is_active_and_tier0_never_waits():
    handled: list[tuple[str, int]] = []
    busy = threading.Event()
    busy.set()

    def handler(job: E.EnhancementJob) -> None:
        handled.append((job.job_id, job.tier))

    budget = E.GpuBudget(detection_active=busy.is_set, defer_seconds=0.01, max_deferrals=2)
    scheduler = E.EnhancementScheduler(handler, queue_size=8, budget=budget, poll_interval=0.005)
    scheduler.start()
    try:
        scheduler.enqueue(_job("tier1", tier=1))
        scheduler.enqueue(_job("tier0", tier=0))
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and ("tier0", 0) not in handled:
            time.sleep(0.005)
        assert ("tier0", 0) in handled
        assert all(job_id != "tier1" for job_id, _ in handled)
        assert scheduler.stats.deferred_detection_busy >= 1
        busy.clear()
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and ("tier1", 1) not in handled:
            time.sleep(0.005)
        assert ("tier1", 1) in handled
    finally:
        scheduler.stop()


def test_tier1_is_dropped_after_the_deferral_budget_is_spent():
    handled: list[str] = []
    budget = E.GpuBudget(detection_active=lambda: True, defer_seconds=0.005, max_deferrals=2)
    scheduler = E.EnhancementScheduler(lambda job: handled.append(job.job_id), queue_size=4, budget=budget, poll_interval=0.005)
    scheduler.start()
    try:
        scheduler.enqueue(_job("tier1-drop", tier=1))
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and scheduler.stats.dropped_detection_busy == 0:
            time.sleep(0.005)
    finally:
        scheduler.stop()
    assert handled == []
    assert scheduler.stats.dropped_detection_busy == 1
    assert "detection active" in (scheduler.stats.last_error or "")


def test_gpu_budget_fails_closed_when_the_detection_probe_breaks():
    def broken() -> bool:
        raise RuntimeError("probe exploded")

    budget = E.GpuBudget(detection_active=broken)
    assert budget.permits(0) is True
    assert budget.permits(1) is False


def _job(job_id: str, tier: int) -> E.EnhancementJob:
    return E.EnhancementJob(
        job_id=job_id,
        alert_id="alert-1",
        camera_id=None,
        tier=tier,
        crop=E.CropRef(alert_id="alert-1", camera_id=None, subject_kind="frame", bbox_xyxy=(0, 0, 24, 24)),
        parent_sha256="f" * 64,
        parent_path="frame.png",
        parent_hash_basis=E.HASH_BASIS_FILE,
        parent_frame=gradient_frame(48, 48),
    )


def test_scheduler_delivers_jobs_to_the_service(tmp_path):
    evidence = tmp_path / "evidence_clips"
    ledger = E.DerivativeLedger(EvidenceLedgerConfig(tmp_path / "chain.jsonl"))
    alert_receipt(ledger, "alert-run")
    original, digest, basis = parent_frame(tmp_path)
    service = E.EnhancementService(ledger, evidence_dir=evidence)
    service.register_parent(
        alert_id="alert-run",
        camera_id="cam-1",
        parent_path=str(original),
        parent_sha256=digest,
        parent_hash_basis=basis,
    )
    scheduler = E.EnhancementScheduler(service.scheduled_handler, queue_size=4, poll_interval=0.005)
    scheduler.start()
    try:
        E.enqueue_alert_enhancement(
            scheduler,
            alert_id="alert-run",
            camera_id="cam-1",
            crops=[
                (
                    E.CropRef(
                        alert_id="alert-run",
                        camera_id="cam-1",
                        subject_kind="face",
                        bbox_xyxy=(4, 4, 60, 60),
                        face_index=0,
                        frame_sequence=5,
                    ),
                    gradient_frame(96, 96),
                )
            ],
            parent_path=str(original),
            parent_sha256=digest,
            parent_hash_basis=basis,
            ops=derivative_ops(),
        )
        assert scheduler.drain(timeout=5.0)
    finally:
        scheduler.stop()
    assert scheduler.stats.completed == 1 and scheduler.stats.failed == 0
    records = E.verify_derivative_chain(ledger.config.path)
    assert len(records) == 2
    assert records[-1]["subjectRef"]["kind"] == "face"
    assert records[-1]["harness"]["status"] == "not_measured"
    assert records[-1]["tier"] == 0
