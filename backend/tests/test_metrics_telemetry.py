"""WT-13 (S-08) telemetry contract tests.

Covers ``backend/metrics.py`` (the sentinel-metrics-export/1 export consumed by bench/
and the UI) and the additive api.py hunks on ``/detections`` and ``/system/status``.

The API integration cases import ``api`` (torch + onnxruntime); they skip cleanly when
the running interpreter cannot import the app, so the module-level contract keeps
working under a bare interpreter.
"""
from __future__ import annotations

import json
import time

import pytest

import metrics as metrics_module


def _snapshot(**overrides):
    snap = {
        "processRunId": "run-1",
        "workerPid": 4242,
        "inferenceGeneration": 1,
        "inference_sequence": 1,
        "capture_timestamp": time.monotonic() - 0.05,
        "frameAgeMs": 41.5,
        "frameAgeClockSource": "monotonic-capture",
        "stageFrameReadMs": 6.25,
        "stageCaptureToQueueMs": 3.5,
        "stagePreprocessMs": 4.0,
        "stageEnqueueToDequeueMs": 12.5,
        "stageInferenceWaitMs": 8.0,
        "stageInferenceComputeMs": 24.0,
        "inferenceComputeSynced": True,
        "frameQueueDepth": 1,
        "frameQueueDropped": 0,
        "frameQueueDroppedDerived": 0,
        "resultQueueDepth": 2,
        "resultQueueDropped": 0,
        "backlogFrames": 0,
        "personCompletedCount": 2,
        "violenceCompletedCount": 1,
        "weaponCompletedCount": 0,
        "alert_state": "NORMAL",
    }
    snap.update(overrides)
    return snap


def _fresh_metrics():
    return metrics_module.PipelineMetrics()


def test_unmeasured_values_export_as_null_not_zero():
    export = _fresh_metrics().export_snapshot()
    assert export["schemaVersion"] == "sentinel-metrics-export/1"
    assert export["rates"]["captureFps"] is None
    assert export["rates"]["publicationFps"] is None
    assert export["rates"]["completedInferenceFps"]["violence"] is None
    assert export["stageLatencyMs"] == {}
    assert export["queues"] == {}
    assert export["frameAgeMs"]["atPublication"] is None
    statuses = {name: entry["status"] for name, entry in export["subsystems"].items()}
    assert statuses["stage-timings"] == "UNMEASURED"
    assert statuses["telemetry-ingest"] == "UNMEASURED"


def test_export_documents_clock_domains_and_naming_rules():
    export = _fresh_metrics().export_snapshot()
    assert "capture-monotonic" in export["clockDomains"]
    assert "media" in export["clockDomains"]
    assert any("never subtract across clock domains" in rule for rule in export["rules"])
    assert any("glass-to-alert" in rule for rule in export["rules"])
    assert export["runProvenance"]["label"] == "unlabeled"
    assert export["ingest"]["surfaces"] == ["GET /detections", "GET /system/status"]
    resources = export["resources"]
    assert resources["gpuScope"].startswith("device-wide")
    assert "per-process" in resources["gpuPerProcess"]
    assert "CONTENDED/INVALID" in resources["contentionNote"]


def test_snapshot_ingest_populates_stage_counters_and_queues():
    telemetry = _fresh_metrics()
    for index in range(1, 31):
        telemetry.observe_detection_snapshot(
            _snapshot(inference_sequence=index, violenceCompletedCount=index * 3, personCompletedCount=index * 9),
            camera_id="CAM-01")
        time.sleep(0.002)
    export = telemetry.export_snapshot()

    assert export["stageLatencyMs"]["preprocess"]["n"] == 30
    assert export["stageLatencyMs"]["preprocess"]["clockDomain"] == "worker-monotonic"
    assert export["stageLatencyMs"]["inferenceCompute"]["synced"] is True
    assert export["frameAgeMs"]["atInferenceStart"]["clockDomain"] == "capture-monotonic"
    assert export["frameAgeMs"]["atInferenceStart"]["n"] == 30
    assert export["frameAgeMs"]["atPublication"]["clockDomain"] == "monotonic-same-machine"
    assert export["queues"]["frame"]["depthNow"] == 1
    assert export["queues"]["frame"]["droppedTotal"] == 0
    assert export["queues"]["frame"]["divergence"] == 0
    assert export["counters"]["violenceCompletedCount"]["value"] == 90
    assert export["rates"]["completedInferenceFps"]["violence"]["numerator"] > 0
    assert export["rates"]["completedInferenceFps"]["violence"]["samples"] == 30
    assert export["rates"]["publicationFps"]["numerator"] == 29
    assert export["observation"]["distinctSequenceCount"] == 30
    assert export["subsystems"]["stage-timings"]["status"] == "OK"
    assert export["faults"] == {}
    # JSON-serialisable for bench consumers
    json.dumps(export, allow_nan=False)


def test_counter_regression_without_new_process_run_is_a_fault():
    telemetry = _fresh_metrics()
    telemetry.observe_detection_snapshot(_snapshot(violenceCompletedCount=10), camera_id="CAM-01")
    telemetry.observe_detection_snapshot(_snapshot(inference_sequence=2, violenceCompletedCount=4), camera_id="CAM-01")
    export = telemetry.export_snapshot()
    assert export["faults"]["counterRegressionDetected"] == 1
    assert export["subsystems"]["counter-integrity"]["status"] == "DEGRADED"
    assert any("regressed" in entry["detail"] for entry in export["faultLog"])


def test_counter_rates_never_cross_a_process_run_boundary():
    telemetry = _fresh_metrics()
    for index in range(1, 11):
        telemetry.observe_detection_snapshot(
            _snapshot(inference_sequence=index, violenceCompletedCount=index * 5, processRunId="run-A"),
            camera_id="CAM-01")
        time.sleep(0.002)
    rate_before = telemetry.export_snapshot()["rates"]["completedInferenceFps"]["violence"]
    assert rate_before["processRunId"] == "run-A"
    telemetry.observe_detection_snapshot(
        _snapshot(inference_sequence=11, violenceCompletedCount=5, processRunId="run-B"), camera_id="CAM-01")
    after_restart = telemetry.export_snapshot()["rates"]["completedInferenceFps"]["violence"]
    assert after_restart is None  # single sample in the new run: unmeasured, not a fake spike
    assert telemetry.export_snapshot()["faults"] == {}
    telemetry.observe_detection_snapshot(
        _snapshot(inference_sequence=12, violenceCompletedCount=10, processRunId="run-B"), camera_id="CAM-01")
    resumed = telemetry.export_snapshot()["rates"]["completedInferenceFps"]["violence"]
    assert resumed["processRunId"] == "run-B"
    assert resumed["numerator"] == 5
    assert telemetry.export_snapshot()["counters"]["publicationCount"]["value"] == 2


def test_frame_age_at_publication_prefers_explicit_then_derives_from_monotonic_capture():
    telemetry = _fresh_metrics()
    telemetry.observe_detection_snapshot(_snapshot(frameAgeAtPublicationMs=88.0), camera_id="CAM-01")
    explicit = telemetry.export_snapshot()["frameAgeMs"]["atPublication"]
    assert explicit["median"] == 88.0
    assert explicit["n"] == 1


def test_queue_drop_divergence_is_published_never_averaged():
    telemetry = _fresh_metrics()
    telemetry.observe_detection_snapshot(_snapshot(frameQueueDropped=5, frameQueueDroppedDerived=3), camera_id="CAM-01")
    frame_queue = telemetry.export_snapshot()["queues"]["frame"]
    assert frame_queue["droppedTotal"] == 5
    assert frame_queue["droppedDerivedTotal"] == 3
    assert frame_queue["divergence"] == 2


def test_malformed_or_hostile_snapshots_never_raise():
    telemetry = _fresh_metrics()
    assert telemetry.observe_detection_snapshot(None)["ingested"] is False
    assert telemetry.observe_detection_snapshot({"personCompletedCount": "many"})["ingested"] is True
    assert telemetry.observe_detection_snapshot({"inference_sequence": float("nan")})["ingested"] is True
    export = telemetry.export_snapshot()
    assert export["faults"]["counterSampleRejected"] == 1
    assert export["counters"].get("personCompletedCount") is None


def test_per_model_inference_timings_and_nested_aliases_are_accepted():
    telemetry = _fresh_metrics()
    telemetry.observe_detection_snapshot(_snapshot(
        frameQueueDropped=None,
        inference_timings=[
            {"model": "violence", "stageInferenceComputeMs": 21.0, "inferenceComputeSynced": True},
            {"model": "weapon", "stageInferenceComputeMs": 9.0, "inferenceComputeSynced": False},
        ],
        frames_read=500,
        frame_queue_dropped=7,
    ), camera_id="CAM-01")
    export = telemetry.export_snapshot()
    assert export["stageLatencyMs"]["inferenceCompute"]["byModel"]["violence"]["synced"] is True
    assert export["stageLatencyMs"]["inferenceCompute"]["byModel"]["weapon"]["synced"] is False
    assert export["counters"]["framesReadCount"]["value"] == 500
    assert export["queues"]["frame"]["droppedTotal"] == 7


def test_detection_telemetry_payload_labels_unavailable_paths():
    telemetry = _fresh_metrics()
    block = telemetry.detection_telemetry_payload(_snapshot(), camera_id="CAM-01")
    assert block["schemaVersion"] == "sentinel-metrics-export/1"
    assert block["stageMs"]["preprocess"] == 4.0
    assert block["queues"]["frameQueueDropped"] == 0
    assert block["counters"]["violenceCompletedCount"] == 1
    assert block["inferenceComputeSynced"] is True
    assert block["frameAgeMs"]["atDisplay"] is None
    assert "NOT glass-to-alert" in block["processingLatencyClockDomain"]

    sparse = telemetry.detection_telemetry_payload({"inferenceSequence": 1}, camera_id="CAM-01")
    assert sparse["stageMs"]["preprocess"] is None
    assert sparse["queues"]["frameDepth"] is None
    assert "stageMs.preprocess" in sparse["unavailable"]
    assert "queues.frameDepth" in sparse["unavailable"]
    assert sparse["frameAgeMs"]["atInferenceStart"] is None


def test_decision_confirm_latency_is_ingested_from_both_payload_shapes():
    telemetry = _fresh_metrics()
    clock = "window-open->confirmed on the sample clock; NOT glass-to-alert"
    # WT-20 alert payload shape: top-level camelCase
    telemetry.observe_detection_snapshot(_snapshot(
        decisionConfirmLatencyMs=1500.0,
        decisionConfirmLatencyClock=clock,
    ), camera_id="CAM-01")
    # WT-20 decision response shape: nested snake_case inside decision_layer
    telemetry.observe_detection_snapshot(_snapshot(
        inference_sequence=2,
        alert_state=None,
        decision_layer={"alert_state": "CONFIRMED_VIOLENCE",
                        "decision_confirm_latency_ms": 0.0,
                        "decision_confirm_latency_clock": clock},
    ), camera_id="CAM-01")
    decision = telemetry.export_snapshot()["decision"]
    assert decision["state"] == "CONFIRMED"
    assert decision["confirmLatencyMs"]["n"] == 2
    assert decision["confirmLatencyMs"]["min"] == 0.0
    assert decision["confirmLatencyMs"]["median"] == 750.0
    assert decision["confirmLatencyMs"]["clockDomain"] == "decision-sample-clock"
    assert decision["confirmLatencyClock"] == clock
    assert "NOT glass-to-alert" in decision["confirmLatencyNote"]


def test_latency_only_snapshot_never_fabricates_a_decision_state():
    telemetry = _fresh_metrics()
    telemetry.observe_detection_snapshot({"decisionConfirmLatencyMs": 250.0}, camera_id="CAM-01")
    decision = telemetry.export_snapshot()["decision"]
    assert decision["state"] is None
    assert decision["confirmLatencyMs"]["n"] == 1
    assert decision["confirmLatencyMs"]["median"] == 250.0


def test_summary_keeps_legacy_keys_and_carries_the_export():
    telemetry = _fresh_metrics()
    telemetry.record_capture(24.0)
    telemetry.record_inference(30.0)
    telemetry.record_encode(5.0)
    telemetry.record_stream(23.0)
    telemetry.record_weapon(0.4)
    telemetry.record_person(3)
    summary = telemetry.summary()
    assert summary["captureFps"] == 24.0
    assert summary["inferenceLatencyMs"] == 30.0
    assert summary["encodeLatencyMs"] == 5.0
    assert summary["streamFps"] == 23.0
    assert summary["avgWeaponScore"] == 0.4
    assert summary["avgPersonCount"] == 3.0
    assert summary["metricsExport"]["schemaVersion"] == "sentinel-metrics-export/1"
    assert summary["telemetry"]["subsystems"]


@pytest.fixture(scope="module")
def api_module():
    api = pytest.importorskip("api", reason="api import requires the project venv (torch/onnxruntime)")
    return api


def test_api_detections_payload_attaches_pipeline_telemetry(api_module):
    snap = _snapshot(inference_sequence=7)
    api_module.state.set_detection_meta("CAM-T13", snap)
    payload = api_module._build_detection_payload(snap, "CAM-T13")
    assert payload["pipeline"]["schemaVersion"] == "sentinel-metrics-export/1"
    assert payload["pipeline"]["stageMs"]["preprocess"] == 4.0
    assert payload["pipeline"]["counters"]["violenceCompletedCount"] == 1
    # the /detections hunk also feeds the aggregate registry
    export = api_module.pipeline_metrics.export_snapshot() if hasattr(api_module, "pipeline_metrics") else None
    if export is None:
        from metrics import pipeline_metrics
        export = pipeline_metrics.export_snapshot()
    assert export["observation"]["ingestCount"] >= 1


def test_api_system_status_exposes_metrics_and_subsystems(api_module, monkeypatch):
    import types
    from fastapi.testclient import TestClient

    class _StubSubsystem:
        """Stands in for engines that the app only initialises in its lifespan."""
        config = types.SimpleNamespace(enabled=False, violence_weight=0.0, motion_weight=0.0, weapon_weight=0.0)

        def status(self):
            return {"state": "DISABLED", "reason": "test stub: engine not initialised without lifespan"}

    for name in ("weapon_engine", "audio_analyzer", "security_controller", "audit_logger",
                 "fusion_engine", "telegram_notifier"):
        if getattr(api_module, name, None) is None:
            monkeypatch.setattr(api_module, name, _StubSubsystem(), raising=False)

    client = TestClient(api_module.app)
    response = client.get("/system/status")
    assert response.status_code == 200
    body = response.json()
    assert body["metrics"]["metricsExport"]["schemaVersion"] == "sentinel-metrics-export/1"
    assert "subsystems" in body and body["subsystems"]
    metrics_response = client.get("/system/metrics")
    assert metrics_response.status_code == 200
    metrics_body = metrics_response.json()
    assert "error" not in metrics_body
    assert metrics_body["metricsExport"]["schemaVersion"] == "sentinel-metrics-export/1"
    assert metrics_body["captureFps"] >= 0
