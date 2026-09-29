"""The ledger must remain one hash chain under concurrent camera finalizers."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
import threading

import pytest

from backend.evidence import (
    ALERT_RECEIPT_TYPE,
    DERIVATIVE_RECORD_TYPE,
    REPORT_RECEIPT_TYPE,
    EvidenceHoldStore,
    EvidenceIntegrityError,
    EvidenceLedger,
    EvidenceLedgerConfig,
    EvidenceRetentionPolicy,
    EvidenceStorageError,
    hash_asset,
    sha256_file,
)


def append(ledger, alert_id):
    return ledger.append_entry(alert={"id": alert_id, "cameraId": "camera-" + alert_id,
                                      "confidence": 90, "severity": "high"},
                               clip_path=None, snapshot_path=None, report_path=None,
                               report_text="Finalized evidence")


def check_chain(path):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    previous = "GENESIS"
    for row in rows:
        assert row["prevHash"] == previous
        expected = hashlib.sha256(json.dumps({k: v for k, v in row.items() if k != "currentHash"},
                                             ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        assert row["currentHash"] == expected
        previous = expected
    return rows


@pytest.mark.parametrize("separate_instances", [False, True])
def test_concurrent_camera_appends_form_one_complete_hash_chain(tmp_path, separate_instances):
    path = tmp_path / "evidence.jsonl"
    common = EvidenceLedger(EvidenceLedgerConfig(path))
    ledgers = [EvidenceLedger(EvidenceLedgerConfig(path)) if separate_instances else common for _ in range(6)]
    start = threading.Barrier(len(ledgers))

    def camera_worker(index):
        start.wait(timeout=5)
        for number in range(8):
            append(ledgers[index], f"{index}-{number}")

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(camera_worker, index) for index in range(6)]
        for future in futures:
            future.result(timeout=15)
    rows = check_chain(path)
    assert len(rows) == 48
    assert len({row["alertId"] for row in rows}) == 48


def test_racing_replays_of_same_alert_are_idempotent(tmp_path):
    path = tmp_path / "evidence.jsonl"
    ledgers = [EvidenceLedger(EvidenceLedgerConfig(path)) for _ in range(8)]
    start = threading.Barrier(8)

    def replay(ledger):
        start.wait(timeout=5)
        return append(ledger, "same-alert")

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(replay, ledger) for ledger in ledgers]
        results = [future.result(timeout=15) for future in futures]
    assert all(row == results[0] for row in results)
    assert len(check_chain(path)) == 1


def test_readers_and_nested_read_helper_do_not_deadlock_during_appends(tmp_path):
    ledger = EvidenceLedger(EvidenceLedgerConfig(tmp_path / "evidence.jsonl"))
    append(ledger, "known")
    start = threading.Barrier(2)

    def reader():
        start.wait(timeout=5)
        for _ in range(30):
            assert ledger.get("known")["alertId"] == "known"

    def writer():
        start.wait(timeout=5)
        for index in range(20):
            append(ledger, str(index))

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(reader), pool.submit(writer)]
        for future in futures:
            future.result(timeout=15)
    assert len(check_chain(ledger.config.path)) == 21


@pytest.mark.parametrize("damage", ["partial_line", "tampered_hash", "forked_previous_hash"])
def test_damaged_ledger_is_not_silently_skipped_or_extended(tmp_path, damage):
    path = tmp_path / "evidence.jsonl"
    ledger = EvidenceLedger(EvidenceLedgerConfig(path))
    first = append(ledger, "known")
    if damage == "partial_line":
        with path.open("a", encoding="utf-8") as output:
            output.write('{"alertId":')
    else:
        changed = dict(first)
        changed["confidence" if damage == "tampered_hash" else "prevHash"] = "changed"
        path.write_text(json.dumps(changed) + "\n", encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(EvidenceIntegrityError, match="record"):
        append(ledger, "must-not-append")
    assert path.read_bytes() == before


def test_nonfinite_metadata_and_missing_alert_id_never_write_record(tmp_path):
    path = tmp_path / "evidence.jsonl"
    ledger = EvidenceLedger(EvidenceLedgerConfig(path))
    for alert in [{"id": "bad", "confidence": float("nan")}, {"confidence": 0.9}]:
        with pytest.raises(ValueError):
            ledger.append_entry(alert=alert, clip_path=None, snapshot_path=None, report_path=None, report_text="")
    assert not path.exists()


def test_valid_final_record_without_newline_is_not_concatenated(tmp_path):
    path = tmp_path / "evidence.jsonl"
    ledger = EvidenceLedger(EvidenceLedgerConfig(path))
    append(ledger, "first")
    path.write_bytes(path.read_bytes().rstrip(b"\r\n"))
    append(ledger, "second")
    assert [row["alertId"] for row in check_chain(path)] == ["first", "second"]


# ─── WT-24 S-07 adversarial + R-4 hardening cases ─────────────────────────────


def test_strict_hash_primitive_never_substitutes_for_missing_artifact(tmp_path):
    # R-4: a declared artifact without a readable file raises; the old code
    # returned the placeholder "N/A" silently.
    with pytest.raises(EvidenceIntegrityError):
        sha256_file(tmp_path / "vanished.mp4")
    assert sha256_file(None) is None


def test_unreadable_declared_asset_is_explicit_failure_not_placeholder(tmp_path):
    path = tmp_path / "evidence.jsonl"
    ledger = EvidenceLedger(EvidenceLedgerConfig(path))
    gone = tmp_path / "snapshot-gone.jpg"
    record = ledger.append_entry(
        alert={"id": "missing-snapshot", "cameraId": "cam", "confidence": 90},
        clip_path=None,
        snapshot_path=gone,
        report_path=None,
        report_text="",
    )
    # The alert receipt still lands (never a dropped alert) but the failure is
    # explicit data: no fake hash, and absence is distinguishable from breakage.
    assert record["snapshotSha256"] == "N/A"
    assert record["snapshotHashStatus"] == "unreadable"
    assert record["clipHashStatus"] == "absent"
    assert record["reportHashStatus"] == "absent"
    assert record["clipSha256"] == "N/A"
    check_chain(path)


def test_hash_asset_classifies_hashed_absent_unreadable(tmp_path):
    real = tmp_path / "clip.mp4"
    real.write_bytes(b"evidence")
    assert hash_asset(real) == (hashlib.sha256(b"evidence").hexdigest(), "hashed")
    assert hash_asset(None) == (None, "absent")
    assert hash_asset(tmp_path / "nope.mp4") == (None, "unreadable")


def test_report_receipt_is_a_followup_record_and_get_returns_primary(tmp_path):
    path = tmp_path / "evidence.jsonl"
    ledger = EvidenceLedger(EvidenceLedgerConfig(path))
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4 report one")
    first = append(ledger, "alert-1")
    receipt = ledger.append_entry(
        alert={"id": "alert-1", "cameraId": "cam", "confidence": 90},
        clip_path=None,
        snapshot_path=None,
        report_path=pdf,
        report_text="",
        record_type=REPORT_RECEIPT_TYPE,
    )
    assert receipt["recordType"] == REPORT_RECEIPT_TYPE
    assert receipt["reportSha256"] == hashlib.sha256(b"%PDF-1.4 report one").hexdigest()
    # get() serves the primary alert receipt only; follow-ups stay queryable.
    assert ledger.get("alert-1") == first
    rows = ledger.records_for("alert-1")
    assert [row["recordType"] for row in rows] == [ALERT_RECEIPT_TYPE, REPORT_RECEIPT_TYPE]
    # Idempotent re-download of identical bytes adds nothing to the chain.
    again = ledger.append_entry(
        alert={"id": "alert-1", "cameraId": "cam", "confidence": 90},
        clip_path=None,
        snapshot_path=None,
        report_path=pdf,
        report_text="",
        record_type=REPORT_RECEIPT_TYPE,
    )
    assert again == receipt
    assert len(ledger.records_for("alert-1")) == 2
    # A rebuilt (different) report is a distinct published artifact -> a new record.
    pdf.write_bytes(b"%PDF-1.4 report two")
    rebuilt = ledger.append_entry(
        alert={"id": "alert-1", "cameraId": "cam", "confidence": 90},
        clip_path=None,
        snapshot_path=None,
        report_path=pdf,
        report_text="",
        record_type=REPORT_RECEIPT_TYPE,
    )
    assert rebuilt["reportSha256"] == hashlib.sha256(b"%PDF-1.4 report two").hexdigest()
    assert len(ledger.records_for("alert-1")) == 3
    assert ledger.get("alert-1") == first
    check_chain(path)


def test_derivative_records_never_shadow_the_alert_receipt(tmp_path):
    path = tmp_path / "evidence.jsonl"
    ledger = EvidenceLedger(EvidenceLedgerConfig(path))
    first = append(ledger, "alert-2")
    ledger.append_record({
        "alertId": "alert-2",
        "recordType": DERIVATIVE_RECORD_TYPE,
        "parentSha256": first["currentHash"],
        "enhancementTier": "tier-1",
    })
    assert ledger.get("alert-2") == first
    # A replayed receipt still resolves to the primary receipt, not a derivative.
    assert append(ledger, "alert-2") == first
    assert len(ledger.records_for("alert-2")) == 2
    check_chain(path)


def test_append_record_requires_identity_and_rejects_nonfinite(tmp_path):
    path = tmp_path / "evidence.jsonl"
    ledger = EvidenceLedger(EvidenceLedgerConfig(path))
    with pytest.raises(ValueError):
        ledger.append_record({"recordType": DERIVATIVE_RECORD_TYPE})
    with pytest.raises(ValueError):
        ledger.append_record({"alertId": "x"})
    with pytest.raises(ValueError):
        ledger.append_record({"alertId": "x", "recordType": DERIVATIVE_RECORD_TYPE,
                              "score": float("inf")})
    assert not path.exists()


def test_disk_full_rolls_back_the_append_and_chain_stays_valid(tmp_path, monkeypatch):
    path = tmp_path / "evidence.jsonl"
    ledger = EvidenceLedger(EvidenceLedgerConfig(path))
    append(ledger, "before")
    before = path.read_bytes()

    def full(*args, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(os, "fsync", full)
    with pytest.raises(EvidenceStorageError):
        append(ledger, "doomed")
    monkeypatch.undo()
    # The failed append left no partial record behind.
    assert path.read_bytes() == before
    append(ledger, "after")
    assert [row["alertId"] for row in check_chain(path)] == ["before", "after"]


def test_hold_store_round_trip_atomicity_and_damage_detection(tmp_path):
    store = EvidenceHoldStore(tmp_path / "holds.json")
    assert store.load() == set()
    store.set_hold("alert-hold", True)
    store.set_hold("alert-other", True)
    store.set_hold("alert-other", False)
    assert store.load() == {"alert-hold"}
    assert not (tmp_path / "holds.json.part").exists()
    (tmp_path / "holds.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(EvidenceIntegrityError):
        store.load()


def test_retention_policy_is_dry_run_and_holds_win_over_age():
    holds = {"alert-held"}
    policy = EvidenceRetentionPolicy(30, holds)
    assert policy.enabled
    old = policy.evaluate("alert-old", "clip", "alert-old.mp4", 45.0)
    assert (old.action, old.reason) == ("prune", "older-than-retention")
    held = policy.evaluate("alert-held", "clip", "alert-held.mp4", 45.0)
    assert (held.action, held.reason) == ("keep", "legal-hold")
    young = policy.evaluate("alert-new", "clip", "alert-new.mp4", 2.0)
    assert (young.action, young.reason) == ("keep", "within-retention")
    disabled = EvidenceRetentionPolicy(None, set())
    assert not disabled.enabled
    assert disabled.evaluate("alert-old", "clip", "x.mp4", 999.0).action == "keep"


def test_no_deletion_path_exists_in_the_retention_planner():
    # The campaign must never delete evidence: the planner is advisory only.
    assert not hasattr(EvidenceRetentionPolicy, "prune")
    assert not hasattr(EvidenceRetentionPolicy, "delete")
    assert not hasattr(EvidenceRetentionPolicy, "apply")
