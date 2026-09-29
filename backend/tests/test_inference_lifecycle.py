"""No-model tests for inference child recovery and media-epoch isolation."""

from collections import deque
import queue
import threading
import time


class FakeProcess:
    def __init__(self, *, target, args, daemon, name, alive_after_start=True,
                 terminate_kills=True, join_kills=True):
        self.target = target
        self.args = args
        self.daemon = daemon
        self.name = name
        self.alive = False
        self.alive_after_start = alive_after_start
        self.terminate_kills = terminate_kills
        self.join_kills = join_kills
        self.join_timeouts = []
        self.terminate_count = 0
        self.closed = False

    def start(self):
        self.alive = self.alive_after_start

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        self.join_timeouts.append(timeout)
        if self.join_kills:
            self.alive = False

    def terminate(self):
        self.terminate_count += 1
        if self.terminate_kills:
            self.alive = False

    def close(self):
        self.closed = True


def _process_factory(created, **options):
    def create(**kwargs):
        process = FakeProcess(**kwargs, **options)
        created.append(process)
        return process

    return create


def _restart_args(api, monkeypatch, *, old_process, process_factory, **overrides):
    monkeypatch.setattr(api, "INFERENCE_RESTART_BACKOFF_SECONDS", (0.0,))
    args = dict(
        camera_id="camera-1",
        old_process=old_process,
        old_stop_event=threading.Event(),
        frame_queue=queue.Queue(),
        result_queue=queue.Queue(),
        inference_worker=lambda *args: None,
        base_config={"device": "cpu", "sentinel": object()},
        outer_stop_event=threading.Event(),
        restart_times=deque(),
        reset_parent_state=lambda: None,
        process_factory=process_factory,
        event_factory=threading.Event,
        reset_lock=threading.Lock(),
        generation_ref={"value": 0},
    )
    args.update(overrides)
    return args


def test_media_epoch_reset_advances_parent_generation_before_accepting_new_results():
    from backend import api

    ready = threading.Event()
    ready.set()
    reset = threading.Event()
    ack = threading.Event()
    ack.set()
    generation = {"value": 0}

    assert api._request_media_epoch_reset(
        ready_event=ready,
        reset_event=reset,
        reset_ack=ack,
        generation_ref=generation,
    )
    assert generation["value"] == 1
    assert reset.is_set()
    assert not ack.is_set()

    results = queue.Queue()
    results.put({"inference_generation": 0, "inference_sequence": 99})
    results.put({"inference_generation": 1, "inference_sequence": 1})
    rendered = api._GenerationResultQueue(results, generation)
    assert rendered.get_nowait()["inference_sequence"] == 1


def test_dead_child_is_reaped_drained_and_restarted_in_a_new_generation(monkeypatch):
    from backend import api

    created = []
    old_process = FakeProcess(target=lambda: None, args=(), daemon=True, name="old")
    args = _restart_args(
        api,
        monkeypatch,
        old_process=old_process,
        process_factory=_process_factory(created),
    )
    args["frame_queue"].put("stale-frame")
    args["result_queue"].put("stale-result")
    resets = []
    args["reset_parent_state"] = lambda: resets.append("camera-1")

    replacement = api._restart_inference_child(**args)

    assert replacement is not None
    assert old_process.join_timeouts == [1.0]
    assert old_process.terminate_count == 0
    assert old_process.closed
    assert args["old_stop_event"].is_set()
    assert args["frame_queue"].empty()
    assert args["result_queue"].empty()
    assert resets == ["camera-1"]
    assert args["generation_ref"]["value"] == 1
    assert replacement[0].args[3]["inference_generation"] == 1
    assert replacement[0].args[3]["ready_event"] is replacement[2]
    assert replacement[0].args[3]["reset_event"] is replacement[3]
    assert replacement[0].args[3]["reset_ack"] is replacement[4]


def test_hung_child_is_terminated_without_overlapping_replacement(monkeypatch):
    from backend import api

    created = []
    old_process = FakeProcess(
        target=lambda: None,
        args=(),
        daemon=True,
        name="hung",
        terminate_kills=False,
        join_kills=False,
    )
    old_process.alive = True
    args = _restart_args(
        api,
        monkeypatch,
        old_process=old_process,
        process_factory=_process_factory(created),
    )

    assert api._restart_inference_child(**args) is None
    assert old_process.join_timeouts == [1.0, 1.0]
    assert old_process.terminate_count == 1
    assert created == []
    assert args["restart_times"] == deque()


def test_restart_budget_and_shutdown_are_hard_limits(monkeypatch):
    from backend import api

    created = []
    old_process = FakeProcess(target=lambda: None, args=(), daemon=True, name="old")
    budget = deque([time.monotonic()])
    args = _restart_args(
        api,
        monkeypatch,
        old_process=old_process,
        process_factory=_process_factory(created),
        restart_times=budget,
    )
    monkeypatch.setattr(api, "INFERENCE_MAX_RESTARTS", 1)
    assert api._restart_inference_child(**args) is None
    assert created == []
    assert not args["old_stop_event"].is_set()

    stop = threading.Event()
    stop.set()
    args = _restart_args(
        api,
        monkeypatch,
        old_process=old_process,
        process_factory=_process_factory(created),
        outer_stop_event=stop,
    )
    assert api._restart_inference_child(**args) is None
    assert created == []
