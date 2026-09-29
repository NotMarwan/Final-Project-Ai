"""Worker integration with deterministic model completions; no weights loaded."""
import queue
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest
import concurrent.futures

import inference
import inference_process
import weapon
import person_detector
from decision_config import load_decision_config
from temporal_frames import FramePacket
from temporal_frames import TemporalWindow


@pytest.mark.parametrize('person_enabled', [False, True])
@pytest.mark.parametrize('envelope_alias', [False, True])
@pytest.mark.parametrize('expired_weapon', [False, True])
def test_worker_passes_capture_timestamp_env_and_only_advances_completed_observations(monkeypatch, person_enabled, envelope_alias, expired_weapon):
    monkeypatch.setenv('WEAPON_MIN_INTERVAL_MS', '500')
    monkeypatch.setenv('WEAPON_INFER_INTERVAL', '4')
    monkeypatch.setattr(inference, 'ViolenceInferencePipeline', lambda *args, **kwargs:
                        SimpleNamespace(enabled=False, disabled_reason='test-disabled'))
    engines = []
    class ImmediateExecutor:
        def __init__(self, **kwargs):
            pass
        def submit(self, function, frame):
            result = function(frame)
            return SimpleNamespace(done=lambda:True, result=lambda:result)
        def shutdown(self, **kwargs):
            pass
    monkeypatch.setattr(concurrent.futures, 'ThreadPoolExecutor', ImmediateExecutor)
    monkeypatch.setattr(person_detector, 'PersonDetector', lambda **kwargs: SimpleNamespace(
        enabled=True, detect=lambda frame: [{'id':'Person 1', 'bbox':[4.8,3.6,24,18], 'confidence':.9}]))
    class FakeWeaponEngine:
        enabled = True
        def __init__(self, config, device):
            self.config, self.frames, self.closed = config, [], False
            engines.append(self)
        def preload(self):
            return True
        def status(self):
            return {'ready': True}
        def process_frame(self, frame, observed_at=None):
            self.frames.append((frame.copy(), observed_at))
        def latest_signal(self):
            count = len(self.frames)
            return {'score': .9 if count < 3 else .1, 'labels':['knife'], 'bbox':[.1,.1,.9,.9],
                    'observation_score':.8 if count < 3 else 0.0, 'observation_valid':not expired_weapon,
                    'observation_id': 1 if count < 3 else 2, 'observed_at':self.frames[-1][1],
                    'completed_at':time.monotonic(), 'reason':'inference-error:ValueError' if count == 2 else 'ok'}
        def close(self):
            self.closed = True
    monkeypatch.setattr(weapon, 'WeaponSignalEngine', FakeWeaponEngine)
    stop = threading.Event()
    results = []
    class ResultQueue:
        def put(self, result, timeout=None):
            results.append(result)
            if len(results) == 4:
                stop.set()
    frames = queue.Queue()
    first = time.monotonic() - 1
    timestamps = [first + i / 30 for i in range(4)]
    policy = load_decision_config().with_updates(violence_threshold=.73)
    for i, captured_at in enumerate(timestamps):
        packet = FramePacket(np.full((36, 48, 3), i, np.uint8), i + 1, captured_at,
                             480, 360, 30.0, policy.to_dict())
        # A deserialized envelope from a package-imported class has identical fields
        # but a different Python identity. Worker logic must honor its contract.
        frames.put(SimpleNamespace(**vars(packet)) if envelope_alias else packet)
    inference_process.inference_worker(frames, ResultQueue(), stop,
                                       {'device':'cpu', 'person_overlay_enabled':person_enabled, 'person_interval':1})
    assert len(engines) == 1 and engines[0].closed
    assert engines[0].config.min_interval_ms == 500 and engines[0].config.interval == 4
    assert [row[1] for row in engines[0].frames] == timestamps
    sequences = [result['inference_sequence'] for result in results]
    if expired_weapon:
        assert sequences == [0,0,0,0]
        assert not any(row['observation_valid'] for row in results)
    else:
        assert sequences[0] > 0 and sequences[0] == sequences[1]
        assert sequences[2] > sequences[1] and sequences[2] == sequences[3]
        assert [row['observation_score'] for row in results] == [.8, .8, 0, 0]
    assert all(row['decision_config']['violence_threshold'] == .73 for row in results)
    assert all(row['video_width'] == 480 and row['video_height'] == 360 for row in results)
    if person_enabled:
        np.testing.assert_allclose(results[-1]['tracks'][0]['bbox'], [48,36,240,180])
    else:
        assert all(row['pipeline_health']['person']['status'] == 'DISABLED' for row in results)
    assert results[1]['pipeline_health']['weapon']['status'] == 'FAILED'
    assert results[2]['pipeline_health']['weapon']['status'] == 'OK'


def test_person_track_scaling_uses_observation_dimensions_and_preserves_input():
    track = {'id':'P1', 'bbox':[-5,10,320,360], 'confidence':.9}
    scaled = inference_process._scale_person_tracks([track, {'bbox':[float('nan'),0,10,10]}],
                                                    (640,360), (1920,1080))
    assert scaled == [{'id':'P1', 'bbox':[0,30,960,1080], 'confidence':.9}]
    assert track['bbox'] == [-5,10,320,360]


@pytest.mark.parametrize('file_media', [False, True])
def test_worker_separates_media_sample_clock_from_capture_latency_and_weapon_age(monkeypatch, file_media):
    violence_calls, weapon_calls = [], []
    class FakeViolence:
        enabled=True
        disabled_reason=''
        last_error=''
        _last_conf=.9
        _last_calibrated_conf=0.0
        _observation_id=1
        _state_lock=threading.Lock()
        window_status={}
        def __init__(self, *args, **kwargs):
            pass
        def process_frame(self, frame, captured_at, nominal_fps):
            violence_calls.append(captured_at)
            self.window_status={'frames_collected':32,'frames_required':32,
                                'span_seconds':1.24,'valid':len(violence_calls)>1}
    class FakeWeapon:
        enabled=True
        def __init__(self, *args, **kwargs):
            pass
        def preload(self):
            return True
        def status(self):
            return {'ready':True}
        def process_frame(self, frame, observed_at):
            weapon_calls.append(observed_at)
        def latest_signal(self):
            return {'score':0,'observation_id':0,'reason':'ok'}
        def close(self):
            pass
    monkeypatch.setattr(inference, 'ViolenceInferencePipeline', FakeViolence)
    monkeypatch.setattr(weapon, 'WeaponSignalEngine', FakeWeapon)
    stop=threading.Event()
    results=[]
    class ResultQueue:
        def put(self, result, timeout=None):
            results.append(result)
            if len(results)==2:
                stop.set()
    frames=queue.Queue()
    captured=[time.monotonic()-1,time.monotonic()-.5]
    media=[1000,1000.04] if file_media else [None,None]
    for i in range(2):
        frames.put(FramePacket(np.zeros((8,8,3),np.uint8),i+1,captured[i],8,8,25,
                               sample_timestamp=media[i]))
    inference_process.inference_worker(frames,ResultQueue(),stop,{'device':'cpu','person_overlay_enabled':False})
    assert violence_calls == (media if file_media else captured)
    assert weapon_calls == captured
    assert [r['capture_timestamp'] for r in results] == captured
    assert all(r['processing_latency_ms'] >= 0 for r in results)
    assert all(r['window_clock_source'] == ('file-media' if file_media else 'monotonic-capture') for r in results)
    assert results[0]['pipeline_health']['violence']['status']=='DEGRADED'
    assert results[1]['pipeline_health']['violence']['status']=='OK'
    assert all(row['violence_conf']==.9 and row['observation_score']==0 for row in results)


def test_slow_file_decode_uses_original_media_span_without_validating_live_drops():
    media, capture = TemporalWindow(32,25), TemporalWindow(32,25)
    for index in range(32):
        frame=np.zeros((1,1,3),np.uint8)
        media.push(100+index/25,frame)
        capture.push(200+index/14,frame)
    assert media.status()['valid']
    assert media.status()['span_seconds'] == pytest.approx(31/25)
    assert not capture.status()['valid']
