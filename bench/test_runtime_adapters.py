import importlib.util
import sys

import bench.runtime as runtime


def test_missing_optional_services_get_disabled_benchmark_adapters(monkeypatch):
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    monkeypatch.delitem(sys.modules, "go2rtc_bridge", raising=False)
    monkeypatch.delitem(sys.modules, "openrouter_reporting", raising=False)

    try:
        adapters = runtime.install_benchmark_adapters()

        assert adapters == ["go2rtc_bridge", "openrouter_reporting"]
        bridge = sys.modules["go2rtc_bridge"].Go2RTCBridge({}, {})
        assert bridge.is_running is False
        bridge.start()
        bridge.stop()
        reports = sys.modules["openrouter_reporting"].DeepSeekReportService()
        assert reports.status()["enabled"] is False
        assert reports.get_cached("alert-1") is None
    finally:
        sys.modules.pop("go2rtc_bridge", None)
        sys.modules.pop("openrouter_reporting", None)
