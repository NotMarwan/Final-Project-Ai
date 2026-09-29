import json

from bench.run import summarize
from bench.runtime import benchmark_models_ready


def test_absent_trace_is_not_zero_fps_or_passed_gate():
    result = summarize([], {}, 100, 2, 5)
    assert result["capture_fps"] is None
    assert result["render_fps"] is None
    assert result["glass_to_alert_ms"] is None
    assert result["complete_gates_passed"] == []


def test_failed_post_is_not_in_success_latency_distribution():
    result = summarize([], {"requests": [{"status": 500, "ms": 1}, {"status": 200, "ms": 400}]}, 100, 2, 5)
    assert result["post_set_threshold_ms"]["p95"] == 400
    assert len(result["post_failures"]) == 1


def test_observed_capture_failure_remains_zero_throughput():
    result = summarize([{"events": [{"stage": "capture", "at": 103, "ok": False, "ms": 2}], "models": []}], {}, 100, 2, 5)
    assert result["capture_fps"]["p50"] == 0


def test_alert_latency_pairs_capture_decision_and_sse_by_alert_id():
    events = [
        {"stage": "alert_decision", "at": 102.1, "ms": None, "alert_id": "a1", "capture_timestamp": 102.0},
        {"stage": "sse_emitted", "at": 102.16, "ms": None, "alert_id": "a1", "alertLatencyMs": 95.4},
    ]
    result = summarize([{"events": events, "models": []}], {}, 100, 0, 5)["alert_latency"]
    assert result["capture_to_decision_ms"]["p50"] == 100.0
    assert result["decision_to_sse_emitted_ms"]["p50"] == 60.0
    assert result["capture_to_sse_emitted_ms"]["p50"] == 160.0
    assert result["alertLatencyMs"]["p50"] == 95.4
    assert result["matched_alert_count"] == 1


def test_alert_latency_keeps_missing_backend_field_unavailable():
    events = [
        {"stage": "alert_decision", "at": 102.1, "ms": None, "alert_id": "a1", "capture_timestamp": 102.0},
        {"stage": "sse_emitted", "at": 102.16, "ms": None, "alert_id": "a1", "alertLatencyMs": None},
    ]
    result = summarize([{"events": events, "models": []}], {}, 100, 0, 5)["alert_latency"]
    assert result["alertLatencyMs"] == {"count": 0, "p05": None, "p50": None, "p95": None, "max": None}


def test_benchmark_readiness_waits_for_requested_inference_models(tmp_path):
    ready_path = tmp_path / "models-ready.json"
    ready_path.write_text(json.dumps({"ready": True, "loaded_models": ["violence"]}), encoding="utf-8")
    assert benchmark_models_ready(tmp_path, all_detection=False)
    assert not benchmark_models_ready(tmp_path, all_detection=True)

    ready_path.write_text(json.dumps({"ready": True, "loaded_models": ["violence", "weapon"]}), encoding="utf-8")
    assert benchmark_models_ready(tmp_path, all_detection=True)
