"""WT-25 incident triage state machine tests (module-level, no API import).

The API module cannot be imported at the baseline (B-1 / SC-10), so the state
machine is verified directly. API-level wiring is covered by the route contract
in backend/api.py and is exercised by the campaign e2e run once the API is
installable.
"""
import os
import sys
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from alert_triage import (  # noqa: E402
    MAX_ACTOR_CHARS,
    MAX_HISTORY_ENTRIES,
    UNKNOWN_ACTOR,
    apply_transition,
    build_record,
    normalize_record,
    reduce_triage,
)


class ReduceTriageTests(unittest.TestCase):
    def test_acknowledge_moves_new_to_in_progress(self):
        self.assertEqual(reduce_triage("new", "acknowledge"), "in_progress")

    def test_hold_then_resume_round_trip(self):
        self.assertEqual(reduce_triage("in_progress", "hold"), "on_hold")
        self.assertEqual(reduce_triage("on_hold", "resume"), "in_progress")

    def test_resolve_is_reachable_from_every_open_state(self):
        for state in ("new", "in_progress", "on_hold"):
            self.assertEqual(reduce_triage(state, "resolve"), "resolved", state)

    def test_reopen_only_from_resolved(self):
        self.assertEqual(reduce_triage("resolved", "reopen"), "in_progress")
        self.assertIsNone(reduce_triage("new", "reopen"))
        self.assertIsNone(reduce_triage("in_progress", "reopen"))

    def test_disallowed_transitions_return_none(self):
        self.assertIsNone(reduce_triage("new", "hold"))
        self.assertIsNone(reduce_triage("in_progress", "acknowledge"))
        self.assertIsNone(reduce_triage("resolved", "resolve"))


class ApplyTransitionTests(unittest.TestCase):
    def test_missing_record_starts_from_new(self):
        record, reason = apply_transition(None, "acknowledge", "viewer")
        self.assertEqual(reason, "ok")
        self.assertEqual(record["state"], "in_progress")
        self.assertEqual(record["action"], "acknowledge")
        self.assertEqual(record["actor"], "viewer")
        self.assertEqual(len(record["history"]), 1)

    def test_conflict_is_reported_and_not_applied(self):
        stored = build_record("new", "acknowledge", "viewer", previous=None)
        stored["state"] = "new"
        record, reason = apply_transition(stored, "hold", "viewer")
        self.assertIsNone(record)
        self.assertEqual(reason, "conflict")

    def test_unknown_action_is_rejected(self):
        record, reason = apply_transition(None, "delete", "viewer")
        self.assertIsNone(record)
        self.assertEqual(reason, "invalid_action")

    def test_corrupt_stored_record_is_ignored(self):
        record, reason = apply_transition({"state": "melted", "action": "acknowledge"}, "acknowledge", "viewer")
        self.assertEqual(reason, "ok")
        self.assertEqual(record["state"], "in_progress")

    def test_history_accumulates_actor_and_timestamp(self):
        first, _ = apply_transition(None, "acknowledge", "viewer")
        second, _ = apply_transition(first, "hold", "admin")
        third, _ = apply_transition(second, "resolve", "admin")
        self.assertEqual([entry["action"] for entry in third["history"]], ["acknowledge", "hold", "resolve"])
        self.assertEqual([entry["actor"] for entry in third["history"]], ["viewer", "admin", "admin"])
        self.assertTrue(all(isinstance(entry["at"], str) and entry["at"] for entry in third["history"]))

    def test_history_is_bounded(self):
        record, reason = apply_transition(None, "acknowledge", "viewer")
        self.assertEqual(reason, "ok")
        for index in range(MAX_HISTORY_ENTRIES * 2):
            action = "hold" if index % 2 == 0 else "resume"
            record, reason = apply_transition(record, action, "viewer")
            self.assertEqual(reason, "ok")
        self.assertEqual(len(record["history"]), MAX_HISTORY_ENTRIES)


class NormalizeRecordTests(unittest.TestCase):
    def test_actor_is_trimmed_and_defaulted(self):
        self.assertEqual(build_record("new", "acknowledge", "  viewer  ")["actor"], "viewer")
        self.assertEqual(build_record("new", "acknowledge", None)["actor"], UNKNOWN_ACTOR)
        self.assertEqual(len(build_record("new", "acknowledge", "x" * 200)["actor"]), MAX_ACTOR_CHARS)

    def test_invalid_records_are_rejected(self):
        for raw in (None, {}, {"state": "new"}, {"state": "new", "action": "explode", "at": "t"},
                    {"state": "new", "action": "resolve", "at": ""}, "new"):
            self.assertIsNone(normalize_record(raw), raw)

    def test_valid_record_round_trips(self):
        stored = build_record("on_hold", "hold", "admin")
        self.assertEqual(normalize_record(stored)["state"], "on_hold")

    def test_history_entries_are_filtered(self):
        stored = build_record("new", "acknowledge", "viewer")
        stored["history"] = [{"action": "acknowledge", "actor": "viewer", "at": "t"}, "junk", 42]
        self.assertEqual(len(normalize_record(stored)["history"]), 1)


if __name__ == "__main__":
    unittest.main()
