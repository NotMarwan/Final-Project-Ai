"""Elapsed-time and worker lifecycle contracts; no model accuracy claims."""
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest
import torch

import weapon
from weapon import WeaponConfig, WeaponSignalEngine


def engine(**overrides):
    return WeaponSignalEngine(WeaponConfig(interval=1, min_interval_ms=0, **overrides), torch.device('cpu'))


def test_decay_depends_on_elapsed_time_not_reads_or_negative_tick_count(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(weapon.time, 'monotonic', lambda: clock[0])
    frequent, sparse = engine(signal_ttl_ms=60000), engine(signal_ttl_ms=60000)
    for e in (frequent, sparse):
        e._update_score(best=.9, labels=['knife'], bbox=[.1, .1, .9, .9])
    for step in range(1, 101):
        clock[0] = 100 + step * .05
        frequent._update_score(best=0, labels=[])
        frequent.latest_signal()
    sparse._update_score(best=0, labels=[])
    assert frequent.latest_signal()['score'] == pytest.approx(.2025, abs=.0001)
    assert sparse.latest_signal()['score'] == frequent.latest_signal()['score']
    assert sparse.latest_signal()['bbox'] is None
    for _ in range(1000):
        sparse.latest_signal()
    assert sparse.latest_signal()['score'] == frequent.latest_signal()['score']


def test_stale_signal_expires_even_without_another_frame(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(weapon.time, 'monotonic', lambda: clock[0])
    e = engine()
    e._update_score(best=.9, labels=['knife'], bbox=[.1, .1, .9, .9])
    clock[0] = 110.0
    signal = e.latest_signal()
    assert signal['score'] == 0 and signal['bbox'] is None and signal['labels'] == []


def test_old_completion_is_not_revived_and_observation_metadata_is_atomic(monkeypatch):
    monkeypatch.setattr(weapon.time, 'monotonic', lambda: 100.0)
    e = engine()
    e._backend = SimpleNamespace(predict=lambda frame: [(.9, 'knife', [.1, .1, .9, .9])])
    e._infer_async(np.zeros((8, 8, 3)), observed_at=80.0)
    signal = e.latest_signal()
    assert signal['observation_id'] == 1
    assert signal['observed_at'] == 80.0 and signal['completed_at'] == 100.0
    assert signal['score'] == 0 and signal['bbox'] is None
    assert signal['observation_valid'] is False
    assert signal['observation_score'] == .9


def test_genuine_negative_keeps_overlay_decay_but_votes_zero(monkeypatch):
    monkeypatch.setattr(weapon.time,'monotonic',lambda:100.0)
    e=engine()
    e._backend=SimpleNamespace(predict=lambda frame:[(.99,'knife',[.1,.1,.9,.9])])
    for _ in range(5):
        e._infer_async(np.zeros((8,8,3)))
    assert e.latest_signal()['score']>.9
    e._backend=SimpleNamespace(predict=lambda frame:[])
    e._infer_async(np.zeros((8,8,3)))
    signal=e.latest_signal()
    assert signal['score']>.9
    assert signal['observation_score']==0 and signal['observation_valid']


def test_negative_completion_increments_observation_but_reads_do_not():
    e = engine()
    e._backend = SimpleNamespace(predict=lambda frame: [])
    e._infer_async(np.zeros((8, 8, 3)))
    assert e.latest_signal()['observation_id'] == 1
    assert e.latest_signal()['observation_id'] == 1
    e._infer_async(np.zeros((8, 8, 3)))
    assert e.latest_signal()['observation_id'] == 2


def test_failure_is_not_a_successful_negative_observation():
    e = engine()
    def fail(frame):
        raise ValueError('bad output')
    e._backend = SimpleNamespace(predict=fail)
    e._infer_async(np.zeros((8, 8, 3)))
    signal = e.latest_signal()
    assert signal['observation_id'] == 0
    assert signal['reason'] == 'inference-error:ValueError'


def test_ultralytics_failure_does_not_look_like_a_negative_prediction():
    backend = weapon._YOLOBackend.__new__(weapon._YOLOBackend)
    backend.device = torch.device('cpu')
    backend.min_confidence = .2
    def fail(*args, **kwargs):
        raise ValueError('backend failure')
    backend._model = SimpleNamespace(predict=fail)
    with pytest.raises(RuntimeError, match='Ultralytics weapon inference failed'):
        backend.predict(np.zeros((8, 8, 3)))


def wait_until(predicate, timeout=2):
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if predicate():
            return
        threading.Event().wait(.005)
    pytest.fail('Timed out waiting for bounded worker')


def test_worker_reused_and_busy_queue_bounded_with_frame_snapshot():
    e = engine()
    entered, release = threading.Event(), threading.Event()
    values = []
    def predict(frame):
        values.append(int(frame[0, 0, 0]))
        entered.set()
        assert release.wait(2)
        return [(.9, 'knife', [.1, .1, .9, .9])]
    e._backend = SimpleNamespace(predict=predict)
    frame = np.zeros((8, 8, 3), dtype=np.uint8)
    stamp = time.monotonic()
    try:
        e.process_frame(frame, observed_at=stamp)
        assert entered.wait(2)
        worker = e._worker
        frame[:] = 9
        for _ in range(100):
            e.process_frame(frame)
        assert e._jobs.qsize() <= 1 and values == [0]
        release.set()
        wait_until(lambda: not e.latest_signal()['inferenceRunning'])
        assert e.latest_signal()['observed_at'] == stamp
        e.process_frame(frame)
        wait_until(lambda: e.latest_signal()['observation_id'] == 2)
        assert e._worker is worker and values == [0, 9]
    finally:
        release.set()
        e.close()
        if e._worker:
            e._worker.join(2)
            assert not e._worker.is_alive()


def test_reset_invalidates_inflight_result_and_does_not_start_second_worker():
    e = engine()
    entered, release = threading.Event(), threading.Event()
    def predict(frame):
        entered.set()
        assert release.wait(2)
        return [(.9, 'knife', [.1, .1, .9, .9])]
    e._backend = SimpleNamespace(predict=predict)
    try:
        e.process_frame(np.zeros((8, 8, 3)))
        assert entered.wait(2)
        worker = e._worker
        e.reset()
        e.process_frame(np.zeros((8, 8, 3)))
        assert e._worker is worker and e.latest_signal()['inferenceRunning']
        release.set()
        wait_until(lambda: not e.latest_signal()['inferenceRunning'])
        signal = e.latest_signal()
        assert signal['score'] == 0 and signal['observation_id'] == 0
    finally:
        release.set()
        e.close()
        if e._worker:
            e._worker.join(2)


def test_monotonic_start_interval_and_timestamp_validation(monkeypatch):
    e = WeaponSignalEngine(WeaponConfig(interval=1, min_interval_ms=2500), torch.device('cpu'))
    e._last_start_monotonic = 99.0
    monkeypatch.setattr(weapon.time, 'monotonic', lambda: 100.0)
    monkeypatch.setattr(weapon.time, 'time', lambda: 99999999.0)
    signal = e.process_frame(np.zeros((8, 8, 3)))
    assert not signal['inferenceRunning'] and e._worker is None
    for stamp in (float('nan'), float('inf'), 101.0):
        with pytest.raises(ValueError):
            e.process_frame(np.zeros((8, 8, 3)), observed_at=stamp)


def test_elapsed_config_env_contract():
    config = WeaponConfig.from_settings({}, {'WEAPON_SCORE_DECAY_HALF_LIFE_MS': '8000',
                                             'WEAPON_SIGNAL_TTL_MS': '20000'})
    assert config.score_decay_half_life_ms == 8000 and config.signal_ttl_ms == 20000


def test_onnx_load_failure_preserves_ultralytics_fallback(monkeypatch):
    def fail(**kwargs):
        raise ValueError('invalid class metadata')
    monkeypatch.setattr(weapon, '_ONNXBackend', fail)
    fallback = SimpleNamespace(predict=lambda frame: [])
    monkeypatch.setattr(weapon, '_YOLOBackend', lambda **kwargs: fallback)
    # Existing model file is not modified or loaded by this test.
    e = engine()
    assert e._ensure_model_loaded()
    assert e._backend is fallback


# ──────────────────────────────────────────────────────────────────────────────
# WT-18 additions: G-05 threshold consolidation, SC-2 null contract, taxonomy
# boundary output, explicit health state. The SC-5 policy now supplies the
# operating values from config/thresholds.toml (DecisionCalibration commit
# c4f6bf9), so these tests exercise the real single authority.
# ──────────────────────────────────────────────────────────────────────────────

import ast
from pathlib import Path

import weapon_fp_log
import weapon_taxonomy


def test_sc5_policy_supplies_every_weapon_knob_from_thresholds_toml():
    policy = weapon.load_decision_policy()
    for name in weapon._POLICY_FIELDS.values():
        assert hasattr(policy, name), f"SC-5 policy is missing {name}"
    config = WeaponConfig.from_settings({}, {})
    # No env/settings input: every knob comes from the policy.
    assert config.threshold_overrides == ()
    assert config.min_confidence == policy.weapon_min_confidence
    assert config.interval == policy.weapon_infer_interval
    assert config.signal_ttl_ms == policy.weapon_signal_ttl_ms


def test_sc5_taxonomy_table_round_trips_through_the_mapping_layer():
    taxonomy = weapon._load_taxonomy()
    table = weapon.load_weapon_taxonomy_table()
    assert taxonomy.group_for("revolver") == "firearm"
    assert taxonomy.group_for("sword") == "edged"
    assert taxonomy.fallback_group == table["fallback_group"]
    assert set(taxonomy.label_filter()) >= {"pistol", "rifle", "shotgun",
                                            "knife", "sword", "revolver"}


def test_weapon_config_defaults_come_from_policy_not_code():
    policy = weapon.load_decision_policy()
    config = WeaponConfig()
    assert config.interval == policy.weapon_infer_interval
    assert config.min_confidence == policy.weapon_min_confidence
    assert config.ema_alpha == policy.weapon_score_ema_alpha
    assert config.input_size == policy.weapon_input_size
    assert config.min_interval_ms == policy.weapon_min_interval_ms
    assert config.realtime_threshold_ms == policy.weapon_realtime_threshold_ms
    assert config.independent_alert_threshold == policy.weapon_independent_alert_threshold
    assert config.score_decay_half_life_ms == policy.weapon_score_decay_half_life_ms
    assert config.signal_ttl_ms == policy.weapon_signal_ttl_ms


def test_env_threshold_overrides_are_tracked_and_surfaced():
    config = WeaponConfig.from_settings({}, {'WEAPON_MIN_CONFIDENCE': '0.35'})
    assert config.min_confidence == pytest.approx(0.35)
    assert 'WEAPON_MIN_CONFIDENCE' in config.threshold_overrides
    e = WeaponSignalEngine(config, torch.device('cpu'))
    status = e.status()
    assert 'WEAPON_MIN_CONFIDENCE' in status['thresholdOverrides']
    assert status['health'] in {'disabled', 'failed', 'loading', 'not-ready', 'degraded-cpu', 'ok'}


def test_policy_missing_sc5_keys_is_a_loud_error_not_a_silent_default():
    with pytest.raises(weapon.WeaponPolicyUnavailable, match='weapon_min_confidence'):
        WeaponConfig.from_settings({}, {}, policy=SimpleNamespace())


def test_weapon_path_holds_no_threshold_literals():
    """G-05 literal checker: the weapon path carries no inline numeric
    thresholds. Retired knob values must not reappear as constants, and the
    config surface must derive every default from the SC-5 policy."""
    root = Path(weapon.__file__).parent
    retired_floats = {0.2, 0.65, 0.45}
    retired_ints = {2500, 500, 5000, 10000}
    for name in ("weapon.py", "weapon_fp_log.py", "weapon_calibration.py",
                 "weapon_taxonomy.py"):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
                    and not isinstance(node.value, bool):
                assert node.value not in retired_floats, \
                    f"{name}:{node.lineno} carries retired threshold literal {node.value}"
                assert node.value not in retired_ints, \
                    f"{name}:{node.lineno} carries retired knob literal {node.value}"
    tree = ast.parse((root / "weapon.py").read_text(encoding="utf-8"))
    checked = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "WeaponConfig":
            checked.append(node)
        if isinstance(node, ast.FunctionDef) and node.name == "load_decision_policy":
            checked.append(node)
    for cls in (item for item in tree.body if isinstance(item, ast.ClassDef)
                and item.name == "WeaponConfig"):
        for item in cls.body:
            if isinstance(item, ast.FunctionDef) and item.name == "from_settings":
                checked.append(item)
    assert len(checked) == 3
    for scope in checked:
        for node in ast.walk(scope):
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
                    and not isinstance(node.value, bool):
                raise AssertionError(
                    f"{scope.name}:{node.lineno} holds numeric literal {node.value}; "
                    "threshold defaults must come from the SC-5 policy"
                )


def test_observation_payload_is_null_without_producer_observation_id():
    e = engine()
    payload = weapon.observation_payload(e.latest_signal())
    assert payload['observation_id'] == 0
    assert payload['weapon_score'] is None
    assert payload['weapon_labels'] is None
    assert payload['weapon_group'] is None
    assert payload['weapon_subtype'] is None
    # A genuine completed negative HAS a producer id: values, not nulls.
    e._backend = SimpleNamespace(predict=lambda frame: [])
    e._infer_async(np.zeros((8, 8, 3)))
    payload = weapon.observation_payload(e.latest_signal())
    assert payload['observation_id'] == 1
    assert payload['weapon_score'] == 0.0
    assert payload['weapon_labels'] == []
    assert payload['weapon_group'] is None


def test_taxonomy_boundary_severity_key_never_flips_on_subtype_mapping_error():
    taxonomy = weapon_taxonomy.default_taxonomy()
    # Every firearm subtype shares one severity key, every edged subtype one.
    firearm_keys = {taxonomy.severity_key(name)
                    for name in ('pistol', 'revolver', 'rifle', 'shotgun')}
    edged_keys = {taxonomy.severity_key(name) for name in ('knife', 'sword')}
    assert len(firearm_keys) == 1 and len(edged_keys) == 1
    assert firearm_keys != edged_keys
    # A mapping error (pistol misread as revolver, knife misread as sword)
    # cannot change the severity key.
    assert taxonomy.severity_key('pistol') == taxonomy.severity_key('revolver')
    assert taxonomy.severity_key('knife') == taxonomy.severity_key('sword')
    # Foreign classes fall back to the coarse fallback group, never dropped.
    assert taxonomy.group_for('handgun') == taxonomy.fallback_group
    assert taxonomy.severity_key('tomahawk') == taxonomy.fallback_group
    # Alias pairs collapse at the alert label; raw subtype stays detail-only.
    assert taxonomy.canonical_label('revolver') == taxonomy.canonical_label('pistol')
    assert taxonomy.canonical_label('sword') == taxonomy.canonical_label('knife')
    assert taxonomy.subtype('Revolver') == 'revolver'


def test_engine_exposes_group_and_subtype_of_best_hit():
    e = engine()
    e._backend = SimpleNamespace(
        predict=lambda frame: [(.4, 'shotgun', [.1, .1, .3, .3]),
                               (.9, 'revolver', [.5, .5, .7, .7])])
    e._infer_async(np.zeros((8, 8, 3)))
    signal = e.latest_signal()
    assert signal['weaponGroup'] == 'firearm'
    assert signal['weaponSubtype'] == 'revolver'
    assert signal['labels'][0] == 'pistol'  # canonical alias label
    assert signal['rawModelScore'] == pytest.approx(.9)


def test_cpu_provider_is_an_explicit_degraded_health_state():
    e = engine()
    e._backend = SimpleNamespace(predict=lambda frame: [])
    e._infer_async(np.zeros((8, 8, 3)))
    status = e.status()
    assert status['health'] == 'degraded-cpu'
    assert status['executionProvider'].startswith('cpu')
