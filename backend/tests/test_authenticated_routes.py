"""WT-28 backend tests — optional-module policy (SC-10) and authenticated routes.

Scoped command:

    py -3.14 -m pytest backend/tests/test_security_contract.py \
        backend/tests/test_authenticated_routes.py -q

No untracked modules (``go2rtc_bridge`` / ``openrouter_reporting``) may be
required for the API to import; when they are absent the affected features must
report an explicit DISABLED state (never silently disappear).
"""
from __future__ import annotations

import importlib
import importlib.abc
import json
import re
import subprocess
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

OPTIONAL_MODULES = ("go2rtc_bridge", "openrouter_reporting")
OPTIONAL_QUALIFIED = tuple(f"backend.{name}" for name in OPTIONAL_MODULES)
API_MODULE = "backend.api"


class _BlockOptionalModules(importlib.abc.MetaPathFinder):
    """Makes the optional integration modules unimportable for one test."""

    def find_spec(self, fullname, path=None, target=None):  # noqa: D102 - protocol
        if fullname in OPTIONAL_MODULES or fullname in OPTIONAL_QUALIFIED:
            raise ModuleNotFoundError(f"blocked for test: {fullname}")
        return None


def _purge_isolated_modules() -> dict[str, types.ModuleType]:
    saved: dict[str, types.ModuleType] = {}
    for name in OPTIONAL_MODULES + OPTIONAL_QUALIFIED + (API_MODULE,):
        if name in sys.modules:
            saved[name] = sys.modules.pop(name)
    return saved


def _restore_isolated_modules(saved: dict[str, types.ModuleType]) -> None:
    for name in list(sys.modules):
        if name in OPTIONAL_MODULES or name in OPTIONAL_QUALIFIED or name == API_MODULE:
            sys.modules.pop(name, None)
    sys.modules.update(saved)


@pytest.fixture
def isolated_api():
    """Import ``backend.api`` in isolation and restore ``sys.modules`` afterwards."""
    saved = _purge_isolated_modules()
    try:
        yield importlib
    finally:
        _restore_isolated_modules(saved)


def test_api_imports_without_optional_modules(isolated_api):
    """The API imports and registers every other route when no optional module exists."""
    blocker = _BlockOptionalModules()
    sys.meta_path.insert(0, blocker)
    try:
        api = importlib.import_module(API_MODULE)
    finally:
        sys.meta_path.remove(blocker)

    assert api.Go2RTCBridge is None
    assert api.DeepSeekReportService is None
    assert api._GO2RTC_IMPORT_ERROR
    assert api._OPENROUTER_IMPORT_ERROR

    paths = {getattr(route, "path", None) for route in api.app.routes}
    assert {
        "/health",
        "/system/status",
        "/security/status",
        "/clips/{alert_id}",
        "/api/clips/list",
        "/download_evidence/{alert_id}",
        "/download_report/{alert_id}",
        "/reports/local/{alert_id}",
        "/reports/deepseek/status",
        "/reports/pdf/{alert_id}",
        "/set_threshold",
        "/set_cooldown",
    } <= paths


def test_feature_health_reports_disabled_when_module_absent(isolated_api):
    """Absent optional features are reported explicitly, never silently."""
    blocker = _BlockOptionalModules()
    sys.meta_path.insert(0, blocker)
    try:
        api = importlib.import_module(API_MODULE)
    finally:
        sys.meta_path.remove(blocker)

    health = api.feature_health()
    assert health["go2rtcBridge"]["state"] == "DISABLED"
    assert health["go2rtcBridge"]["module"] == "go2rtc_bridge"
    assert "go2rtc_bridge" in health["go2rtcBridge"]["reason"]
    assert health["openrouterReporting"]["state"] == "DISABLED"
    assert health["openrouterReporting"]["reason"]

    status = api.deepseek_service.status()
    assert status["available"] is False
    assert status["state"] == "DISABLED"
    assert status["apiKeyPresent"] is False
    # Generation refuses loudly instead of pretending to work.
    with pytest.raises(ValueError) as raised:
        api.deepseek_service.generate({"id": "alert-1"})
    assert "DISABLED" in str(raised.value)
    # The cached-report read path still degrades to the local report fallback.
    assert api.deepseek_service.get_cached("alert-1") is None
    # WebRTC routes carry the explicit disabled explanation.
    assert "DISABLED" in api._webrtc_bridge_unavailable_detail()


def test_feature_enabled_when_module_present(isolated_api):
    """A present optional module is used and reported READY (fake module in test scope)."""

    class FakeBridge:
        def __init__(self, config, env):
            self.config = config
            self.env = env
            self.is_running = False

        def start(self):
            self.is_running = True

    class FakeDeepSeekReportService:
        def __init__(self, cache_dir=None):
            self.cache_dir = cache_dir

        def status(self):
            return {"available": True, "state": "READY", "apiKeyPresent": True}

        def get_cached(self, alert_id):
            return None

    fake_bridge_module = types.ModuleType("go2rtc_bridge")
    fake_bridge_module.Go2RTCBridge = FakeBridge
    fake_reporting_module = types.ModuleType("openrouter_reporting")
    fake_reporting_module.DeepSeekReportService = FakeDeepSeekReportService
    saved = {name: sys.modules.get(name) for name in OPTIONAL_MODULES}
    sys.modules["go2rtc_bridge"] = fake_bridge_module
    sys.modules["openrouter_reporting"] = fake_reporting_module
    sys.modules.pop(API_MODULE, None)
    try:
        api = importlib.import_module(API_MODULE)
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    assert api.Go2RTCBridge is FakeBridge
    assert api.DeepSeekReportService is FakeDeepSeekReportService
    assert isinstance(api.deepseek_service, FakeDeepSeekReportService)
    health = api.feature_health()
    assert health["go2rtcBridge"]["state"] == "READY"
    assert health["go2rtcBridge"]["reason"] is None
    assert health["openrouterReporting"]["state"] == "READY"
    assert health["openrouterReporting"]["reason"] is None


@pytest.fixture
def api_without_optional_modules(isolated_api):
    """``backend.api`` imported with the optional modules forced absent."""
    blocker = _BlockOptionalModules()
    sys.meta_path.insert(0, blocker)
    try:
        yield importlib.import_module(API_MODULE)
    finally:
        sys.meta_path.remove(blocker)


@pytest.fixture
def client_for(api_without_optional_modules):
    """Return a factory: ``client_for(api_key)`` -> TestClient with that credential."""
    from backend.security import AccessConfig, AccessController

    clients = []

    def factory(api_key: str = "test-key"):
        importlib.import_module("fastapi.testclient")  # noqa: F401 - availability check
        from fastapi.testclient import TestClient

        api_without_optional_modules.security_controller = AccessController(AccessConfig(api_key))
        client = TestClient(api_without_optional_modules.app)
        clients.append(client)
        return client

    try:
        yield factory
    finally:
        for client in clients:
            client.close()


MUTATING_ROUTES = (
    ("POST", "/api/webrtc/CAM-01/whep", None),
    ("PATCH", "/api/webrtc/CAM-01/whep", None),
    ("POST", "/webrtc/offer/CAM-01", {"sdp": "v=0", "type": "offer"}),
    ("POST", "/demo_start/EXAMPLE-01", None),
    ("DELETE", "/demo_stop/EXAMPLE-01", None),
    ("POST", "/api/analyze", {"category": "violence", "context": {}}),
    ("POST", "/alerts/alert-1/triage", {"action": "acknowledge"}),
    ("POST", "/reports/pdf/alert-1", None),
    ("POST", "/audio/analyze", {"audio_base64": "", "filename": "test.wav"}),
    ("POST", "/api/categories/violence/toggle?enabled=true", None),
    ("POST", "/set_threshold", {"threshold": 0.5}),
    ("POST", "/set_cooldown", {"cooldown": 30}),
    ("POST", "/decision_layer/reset", None),
    ("POST", "/notifications/telegram/test", None),
    ("POST", "/reports/deepseek/test", None),
    ("POST", "/reports/deepseek/alert-1", None),
    ("POST", "/reports/local/alert-1", None),
)


@pytest.mark.parametrize("method,path,body", MUTATING_ROUTES)
def test_mutating_routes_reject_missing_credential(client_for, method, path, body):
    """A configured key makes every mutating route reject an anonymous request (401)."""
    client = client_for("test-key")
    response = client.request(method, path, json=body)
    assert response.status_code == 401, f"{method} {path} -> {response.status_code}"


@pytest.mark.parametrize("method,path,body", MUTATING_ROUTES)
def test_mutating_routes_authorize_before_validation(client_for, method, path, body):
    """Authentication precedes input validation and mutation: unknown ids also yield 401."""
    client = client_for("test-key")
    unknown = path.replace("CAM-01", "CAM-UNKNOWN").replace("EXAMPLE-01", "NOPE").replace("alert-1", "no-such-alert")
    response = client.request(method, unknown, json=body)
    assert response.status_code == 401, f"{method} {unknown} -> {response.status_code}"


def test_authorized_webrtc_mutation_reaches_disabled_feature(client_for):
    """With a valid key the disabled optional feature answers (auth ran first, no 401)."""
    client = client_for("test-key")
    response = client.post("/api/webrtc/CAM-01/whep", content=b"v=0", headers={"X-API-Key": "test-key"})
    assert response.status_code == 503
    assert "DISABLED" in response.json()["detail"]


def test_webrtc_offer_rejects_unlisted_camera(client_for):
    client = client_for("test-key")
    response = client.post(
        "/webrtc/offer/CAM-UNKNOWN",
        json={"sdp": "v=0", "type": "offer"},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 404
    assert "not configured" in response.json()["detail"]


def test_webrtc_offer_error_detail_is_sanitized(client_for, api_without_optional_modules):
    """A handler failure returns a stable detail and never echoes internals."""

    class ExplodingManager:
        available = True

        async def handle_offer(self, *_args, **_kwargs):
            raise RuntimeError("internal-secret-detail")

    api = api_without_optional_modules
    api._webrtc_manager = ExplodingManager()
    client = client_for("test-key")
    response = client.post(
        "/webrtc/offer/CAM-01",
        json={"sdp": "v=0", "type": "offer"},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 500
    assert response.json()["detail"] == "WebRTC offer failed"
    assert "internal-secret-detail" not in response.text


def test_demo_mode_is_read_only_and_rejects_wrong_key(client_for):
    """Without an admin key, demo inference workers stay closed; a bad key is 401."""
    demo_client = client_for("")
    assert demo_client.post("/demo_start/EXAMPLE-01").status_code == 503
    assert demo_client.delete("/demo_stop/EXAMPLE-01").status_code == 503
    # Other admin-only mutations stay closed in demo mode (stable 503 contract).
    assert demo_client.post("/set_threshold", json={"threshold": 0.5}).status_code == 503
    assert demo_client.post("/reports/deepseek/test").status_code == 503
    # A configured key rejects the wrong credential before anything else.
    keyed_client = client_for("test-key")
    response = keyed_client.post("/demo_start/NOPE", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401


def test_demo_start_does_not_spawn_worker_without_credential(client_for, api_without_optional_modules):
    """A rejected request must not reach the mutation (no worker thread started)."""
    api = api_without_optional_modules
    client = client_for("test-key")
    assert api.state.is_demo_worker_running("EXAMPLE-01") is False
    assert client.post("/demo_start/EXAMPLE-01").status_code == 401
    assert api.state.is_demo_worker_running("EXAMPLE-01") is False


def test_audio_payload_is_bounded():
    """The audio analysis request model carries the payload cap."""
    api = importlib.import_module(API_MODULE)
    with pytest.raises(Exception):
        api.AudioAnalysisRequest(audio_base64="A" * 8_000_001)


def test_security_session_matches_frontend_contract(client_for):
    """GET /security/session returns exactly {role} and 401 for a bad credential."""
    client = client_for("test-key")
    anonymous = client.get("/security/session")
    assert anonymous.status_code == 401
    wrong = client.get("/security/session", headers={"X-API-Key": "wrong"})
    assert wrong.status_code == 401
    verified = client.get("/security/session", headers={"X-API-Key": "test-key"})
    assert verified.status_code == 200
    assert verified.json() == {"role": "admin"}


def test_security_session_reports_viewer_in_demo_mode(client_for):
    """No configured key -> viewer session (dashboard shows the read-only state)."""
    client = client_for("")
    response = client.get("/security/session")
    assert response.status_code == 200
    assert response.json() == {"role": "viewer"}


def test_security_session_route_is_registered(api_without_optional_modules):
    paths = {getattr(route, "path", None) for route in api_without_optional_modules.app.routes}
    assert "/security/session" in paths


def _fake_request(host: str = "127.0.0.1"):
    from starlette.requests import Request

    return Request({"type": "http", "method": "GET", "path": "/alerts", "headers": [], "client": (host, 12345)})


def test_stream_slot_cap_and_rate_limit_return_429(api_without_optional_modules):
    """Public read streams are bounded: global concurrency cap and per-client rate."""
    from fastapi import HTTPException

    api = api_without_optional_modules
    request = _fake_request()
    limits = api._STREAM_LIMITS["sse"]
    try:
        # Fill the per-client window while releasing concurrency (connect/disconnect churn).
        for _ in range(limits["per_client_per_minute"]):
            api._acquire_stream_slot(request, "sse")
            api._release_stream_slot()
        api._stream_subscribers = limits["max_subscribers"]
        with pytest.raises(HTTPException) as raised:
            api._acquire_stream_slot(_fake_request("10.0.0.9"), "sse")
        assert raised.value.status_code == 429
        assert raised.value.headers.get("Retry-After") == "5"
        api._stream_subscribers = 0
        with pytest.raises(HTTPException) as rate_limited:
            api._acquire_stream_slot(request, "sse")
        assert rate_limited.value.status_code == 429
        assert rate_limited.value.headers.get("Retry-After") == "30"
    finally:
        api._stream_subscribers = 0
        api._stream_attempts.clear()


def test_release_stream_slot_returns_capacity(api_without_optional_modules):
    api = api_without_optional_modules
    api._stream_subscribers = 0
    api._stream_attempts.clear()
    api._acquire_stream_slot(_fake_request(), "sse")
    assert api._stream_subscribers == 1
    api._release_stream_slot()
    assert api._stream_subscribers == 0


def test_stream_routes_answer_429_when_capacity_is_reached(client_for, api_without_optional_modules):
    """The cap is wired into the stream handlers themselves."""
    api = api_without_optional_modules
    client = client_for("")
    try:
        api._stream_subscribers = api._STREAM_LIMITS["sse"]["max_subscribers"]
        api._stream_attempts.clear()
        alerts = client.get("/alerts")
        assert alerts.status_code == 429
        assert alerts.headers.get("Retry-After") == "5"
        detections = client.get("/detections?camera_id=EXAMPLE-01")
        assert detections.status_code == 429
        api._stream_subscribers = api._STREAM_LIMITS["mjpeg"]["max_subscribers"]
        feed = client.get("/video_feed?camera_id=EXAMPLE-01")
        assert feed.status_code == 429
    finally:
        api._stream_subscribers = 0
        api._stream_attempts.clear()


CREDENTIAL_SHAPES = (
    ("groq", re.compile(rb"gsk_[A-Za-z0-9]{30,}")),
    ("openrouter", re.compile(rb"sk-or-v1-[A-Za-z0-9]{32,}")),
    ("openai_project", re.compile(rb"sk-proj-[A-Za-z0-9_-]{40,}")),
    ("github", re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}")),
    ("aws", re.compile(rb"AKIA[0-9A-Z]{16}")),
    ("telegram_bot_token", re.compile(rb"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b")),
)


def staged_distribution_credential_findings(stage_root: Path) -> list[dict]:
    """Return credential findings in a staged distribution tree (paths + kinds only).

    A staged/packaged distribution must never contain dotenv files or
    token-shaped values; see the WT-28 audit section on distribution secrets.
    """
    findings: list[dict] = []
    if not stage_root.exists():
        return findings
    for path in sorted(p for p in stage_root.rglob("*") if p.is_file()):
        kinds: list[str] = []
        if path.name == ".env" or path.suffix == ".env":
            kinds.append("dotenv-file")
        data = path.read_bytes()[:2_000_000]
        kinds.extend(f"pattern:{name}" for name, pattern in CREDENTIAL_SHAPES if pattern.search(data))
        if kinds:
            findings.append({"path": path.relative_to(stage_root).as_posix(), "kinds": kinds})
    return findings


def test_packaging_guard_flags_env_and_credentials_in_staged_distribution(tmp_path):
    stage = tmp_path / "win-unpacked"
    (stage / "backend").mkdir(parents=True)
    (stage / "backend" / ".env").write_text("ADMIN_API_KEY=placeholder\n", encoding="utf-8")
    (stage / "backend" / "config.yml").write_text(
        "telegram:\n  bot_token: \"1234567890:AAFakeTokenShapeForTheGuardTest0000000\"\n", encoding="utf-8"
    )
    findings = staged_distribution_credential_findings(stage)
    flagged = {item["path"] for item in findings}
    assert "backend/.env" in flagged
    assert "backend/config.yml" in flagged
    kinds = {kind for item in findings for kind in item["kinds"]}
    assert "dotenv-file" in kinds
    assert "pattern:telegram_bot_token" in kinds
    # The guard reports kinds/paths only — never the value.
    assert all("AAFakeTokenShape" not in json.dumps(item) for item in findings)


def test_packaging_guard_accepts_clean_staged_distribution(tmp_path):
    stage = tmp_path / "win-unpacked"
    (stage / "backend").mkdir(parents=True)
    (stage / "backend" / "api.py").write_text("print('clean')\n", encoding="utf-8")
    assert staged_distribution_credential_findings(stage) == []
    assert staged_distribution_credential_findings(tmp_path / "missing") == []


def test_staged_distribution_in_this_tree_is_clean():
    """Guard for packaged output that exists in the tree (absent in a clean checkout)."""
    stage = REPO_ROOT / "desktop" / "dist"
    if not stage.exists():
        pytest.skip("no staged desktop distribution in this worktree")
    findings = staged_distribution_credential_findings(stage)
    assert findings == [], f"staged distribution contains credential material: {findings}"


def test_report_pdf_generation_is_admin_and_cached_reads_are_chained(client_for, api_without_optional_modules, monkeypatch, tmp_path):
    """PDF creation is a POST mutation; the viewer GET only serves a hashed receipt."""
    from unittest.mock import Mock
    from backend.evidence import EvidenceLedger, EvidenceLedgerConfig, REPORT_RECEIPT_TYPE

    api = api_without_optional_modules
    alert = {
        "id": "alert-reg-1",
        "timestamp": "01:02:03 UTC",
        "isoTime": "2026-09-29T01:02:03+00:00",
        "confidence": 87.5,
        "type": "Violence",
        "severity": "high",
        "cameraId": "CAM-01",
        "location": "Test zone",
    }
    api.state.register_alert(alert)
    api.state.store_report_text(alert["id"], "تقرير واقعة محلي موثوق من سجل الوقائع.", source="local_facts")
    monkeypatch.setattr(api, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(api, "EVIDENCE_DIR", tmp_path / "evidence")
    ledger = EvidenceLedger(EvidenceLedgerConfig(tmp_path / "chain.jsonl"))
    monkeypatch.setattr(api, "evidence_ledger", ledger)
    monkeypatch.setattr(api, "audit_logger", Mock())
    received_sources = []

    def fake_builder(**kwargs):
        received_sources.append(kwargs["report_source"])
        pdf = b"%PDF-1.4\\nlocal report"
        kwargs["output_path"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["output_path"].write_bytes(pdf)
        return pdf

    monkeypatch.setattr(api, "build_incident_pdf", fake_builder)
    admin = client_for("test-key")
    headers = {"X-API-Key": "test-key"}

    # Even an administrator's GET is read-only and cannot invoke the builder.
    missing = admin.get("/download_report/alert-reg-1", headers=headers)
    assert missing.status_code == 404
    assert received_sources == []

    generated = admin.post("/reports/pdf/alert-reg-1", headers=headers)
    assert generated.status_code == 200, generated.text[:400]
    assert generated.content.startswith(b"%PDF")
    assert received_sources == ["local_facts"]
    records = ledger.records_for("alert-reg-1")
    assert [record["recordType"] for record in records] == [REPORT_RECEIPT_TYPE]

    viewer = client_for("")
    cached = viewer.get("/download_report/alert-reg-1")
    assert cached.status_code == 200, cached.text[:400]
    assert cached.content.startswith(b"%PDF")
    assert received_sources == ["local_facts"]
    api.audit_logger.record.assert_any_call(
        "report_pdf_generate", "success", role="admin", alert_id="alert-reg-1",
        details={"reportSha256": records[0]["reportSha256"]},
    )
    api.audit_logger.record.assert_any_call(
        "report_pdf_read", "success", role="viewer", alert_id="alert-reg-1",
        details={"artifact": "report-pdf", "artifactSha256": records[0]["reportSha256"],
                 "ledgerSha256": records[0]["reportSha256"]},
    )


def test_concurrent_report_generation_publishes_one_chained_pdf(client_for, api_without_optional_modules, monkeypatch, tmp_path):
    """Concurrent admin requests cannot create duplicate receipts or remove the winner's PDF."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from time import sleep
    from unittest.mock import Mock

    from backend.evidence import EvidenceLedger, EvidenceLedgerConfig, REPORT_RECEIPT_TYPE

    api = api_without_optional_modules
    alert = {
        "id": "alert-pdf-race-1",
        "timestamp": "01:02:03 UTC",
        "isoTime": "2026-09-29T01:02:03+00:00",
        "confidence": 87.5,
        "type": "Violence",
        "severity": "high",
        "cameraId": "CAM-01",
        "location": "Test zone",
    }
    api.state.register_alert(alert)
    api.state.store_report_text(alert["id"], "Recorded facts.", source="local_facts")
    monkeypatch.setattr(api, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(api, "EVIDENCE_DIR", tmp_path / "evidence")
    ledger = EvidenceLedger(EvidenceLedgerConfig(tmp_path / "chain.jsonl"))
    monkeypatch.setattr(api, "evidence_ledger", ledger)
    monkeypatch.setattr(api, "audit_logger", Mock())
    builder_calls = 0

    def slow_builder(**kwargs):
        nonlocal builder_calls
        builder_calls += 1
        sleep(0.1)
        pdf = b"%PDF-1.4\nconcurrent report"
        kwargs["output_path"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["output_path"].write_bytes(pdf)
        return pdf

    monkeypatch.setattr(api, "build_incident_pdf", slow_builder)
    first = client_for("test-key")
    second = client_for("test-key")
    headers = {"X-API-Key": "test-key"}
    start = Barrier(2)

    def generate(client):
        start.wait(timeout=5)
        return client.post("/reports/pdf/alert-pdf-race-1", headers=headers)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(generate, (first, second)))

    assert sorted(response.status_code for response in responses) == [200, 409]
    assert builder_calls == 1
    receipt_records = [
        record for record in ledger.records_for("alert-pdf-race-1")
        if record.get("recordType") == REPORT_RECEIPT_TYPE
    ]
    assert len(receipt_records) == 1
    output_path = tmp_path / "reports" / "alert-pdf-race-1.pdf"
    assert output_path.is_file()
    assert output_path.read_bytes().startswith(b"%PDF")
    assert receipt_records[0]["reportSha256"] == api._evidence_file_sha(output_path)


def test_admin_analysis_reaches_detector_without_real_inference(client_for, api_without_optional_modules, monkeypatch):
    from types import SimpleNamespace

    api = api_without_optional_modules

    class Detector:
        config = SimpleNamespace(violence_threshold=0.5)

        def analyze_context(self, _context, category):
            return {category: 0.75}

        def get_category_severity(self, _category):
            return "high"

    monkeypatch.setattr(api, "category_detector", Detector())
    monkeypatch.setattr(api, "parse_detection_context", lambda _context: object())
    client = client_for("test-key")
    response = client.post(
        "/api/analyze",
        json={"category": "violence", "context": {}},
        headers={"X-API-Key": "test-key"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["triggered"] is True


def test_admin_mutations_fail_closed_without_configured_key(client_for, api_without_optional_modules):
    api = api_without_optional_modules
    api.state.register_alert({"id": "alert-auth-1", "triage": None})
    demo_viewer = client_for("")
    assert demo_viewer.post("/api/analyze", json={"category": "violence", "context": {}}).status_code == 503
    assert demo_viewer.post("/alerts/alert-auth-1/triage", json={"action": "acknowledge"}).status_code == 503


def test_api_imports_from_repo_root_as_package():
    """Acceptance: a fresh interpreter in the repo root imports the committed API."""
    result = subprocess.run(
        [sys.executable, "-c", "import backend.api; print('ok')"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, result.stderr[-4000:]
    assert "ok" in result.stdout
