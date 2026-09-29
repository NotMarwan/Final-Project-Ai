"""S-14 scoped tests: offline Arabic facts-only report (F-28) correctness edges.

Run: py -m unittest tests.test_local_forensics -v   (or python -m unittest ...)
"""
from __future__ import annotations

import re
import socket
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import local_forensics  # noqa: E402
from local_forensics import build_local_report  # noqa: E402

# Arabic diacritics differ across emitters (e.g. shadda vs fatha+shadda); substring
# checks compare diacritic-free text. Exact equality checks stay byte-exact.
_DIACRITICS = re.compile(r"[ً-ْٰـ]")


class _Case(unittest.TestCase):
    @staticmethod
    def _norm(value):
        return _DIACRITICS.sub("", value) if isinstance(value, str) else value

    def assertIn(self, member, container, msg=None):  # noqa: N802
        super().assertIn(self._norm(member), self._norm(container), msg)

    def assertNotIn(self, member, container, msg=None):  # noqa: N802
        super().assertNotIn(self._norm(member), self._norm(container), msg)

EVENT = {
    "id": "alert-1",
    "cameraId": "cam-7",
    "isoTime": "2026-09-29T12:00:00+00:00",
    "timestamp": "12:00:00 UTC",
    "alertState": "CONFIRMED",
    "confirmRule": "sustained",
    "personCount": 2,
    "confidence": 87.5,
    "rawModelConfidence": 0.875,
    "calibratedConfidence": None,
    "calibrationStatus": "unverified",
    "fusionScore": 0.91,
    "fusionModel": "rule_based",
    "motionScore": 0,
    "weaponScore": 0.0,
    "threatType": "weapon",
    "type": "Weapon",
    "weaponLabels": ["knife", "knife", " "],
    "alertLatencyMs": None,
}


def make_alert(**overrides):
    alert = {**EVENT, **overrides}
    return alert


class FactsInterpretationsUnknowns(_Case):
    def test_sections_present_in_order(self):
        text = build_local_report(make_alert())
        facts = text.index("أولاً: الحقائق المسجلة")
        interp = text.index("ثانياً: تفسيرات النموذج")
        unknown = text.index("ثالثاً: معلومات غير متاحة أو غير معروفة")
        limits = text.index("حدود التقرير")
        self.assertTrue(facts < interp < unknown < limits)

    def test_report_never_claims_image_analysis(self):
        text = build_local_report(make_alert())
        self.assertIn("لم يُجرَ تحليل لغوي بصري للصورة", text)
        self.assertIn("لم يُجرَ أي تحليل للصور", text)
        for forbidden in ("يظهر في الصورة", "تُظهر اللقطة", "يُرى في الفيديو", "تم رصد شخص يحمل"):
            self.assertNotIn(forbidden, text)

    def test_model_scores_are_labelled_unverified(self):
        text = build_local_report(make_alert())
        self.assertIn("غير مُتحقَّق منها", text)
        self.assertIn("لا توجد معايرة مسجَّلة", text)
        # interpretation header must appear before any score value line
        self.assertLess(text.index("ثانياً: تفسيرات النموذج"), text.index("درجة الثقة (confidence)"))

    def test_calibrated_status_is_honoured_not_flattened(self):
        text = build_local_report(make_alert(calibratedConfidence=71.2, calibrationStatus="calibrated"))
        self.assertIn("معايرة مسجَّلة (calibrated)", text)
        self.assertIn("71.20", text)

    def test_null_scores_stay_absent_not_zero(self):
        text = build_local_report(make_alert(confidence=None, fusionScore=None, motionScore=None, weaponScore=None))
        self.assertIn("درجة الثقة: لم تُسجَّل", text)
        self.assertIn("درجة الاندماج: لم تُسجَّل", text)
        self.assertIn("النافذة الزمنية", text)
        self.assertNotIn("(confidence): 0", text)

    def test_observed_zero_is_preserved(self):
        text = build_local_report(make_alert())
        self.assertIn("درجة الحركة (motionScore): 0.00", text)
        self.assertIn("إشارة السلاح (weaponScore): 0.0", text)

    def test_weapon_labels_deduped_and_marked_interpretation(self):
        text = build_local_report(make_alert())
        self.assertEqual(text.count("knife"), 1)  # duplicates collapsed to one listed label
        self.assertIn("تسميات نموذجية، لا تُحتسب كوقائع", text)


class TimeWindowScopeDuplicates(_Case):
    def test_duplicate_ids_counted_once(self):
        alert = make_alert(faceSummary={
            "enabled": True,
            "totalFaces": 3,
            "unknownIds": ["U-1", "U-1", "U-2"],
            "unknownDetails": [
                {"id": "U-1", "firstSeenAt": "2026-09-29T11:59:30+00:00", "lastSeenAt": "2026-09-29T12:00:10+00:00", "durationFrames": 20, "hitStreak": 5},
                {"id": "U-1", "firstSeenAt": "2026-09-29T11:59:30+00:00", "lastSeenAt": "2026-09-29T12:00:10+00:00", "durationFrames": 20, "hitStreak": 5},
            ],
        })
        text = build_local_report(alert)
        self.assertIn("2 من أصل 5 صفوف مسجّلة", text)  # U-1, U-2 unique out of 3+2 rows

    def test_time_window_covers_event_and_observations(self):
        alert = make_alert(faceSummary={
            "enabled": True,
            "unknownIds": ["U-1"],
            "unknownDetails": [
                {"id": "U-1", "firstSeenAt": "2026-09-29T11:59:30+00:00", "lastSeenAt": "2026-09-29T12:00:10+00:00"},
            ],
        })
        text = build_local_report(alert)
        self.assertIn("2026-09-29 11:59:30 UTC ← 2026-09-29 12:00:10 UTC", text)

    def test_stale_observations_flagged_and_excluded_from_count(self):
        alert = make_alert(faceSummary={
            "enabled": True,
            "unknownIds": ["U-old", "U-1"],
            "unknownDetails": [
                {"id": "U-old", "firstSeenAt": "2026-09-29T10:00:00+00:00", "lastSeenAt": "2026-09-29T10:05:00+00:00"},
                {"id": "U-1", "firstSeenAt": "2026-09-29T11:59:30+00:00", "lastSeenAt": "2026-09-29T12:00:10+00:00"},
            ],
        })
        text = build_local_report(alert)
        self.assertIn("ملاحظات قديمة مستثناة من العد: 1", text)
        self.assertIn("300 ثانية", text)  # rule is visible in the report
        self.assertIn("قديمة — مستثناة من العد", text)
        self.assertIn("1 من أصل 4 صفوف مسجّلة", text)

    def test_camera_scope_statement_present(self):
        text = build_local_report(make_alert())
        self.assertIn("النطاق: هذه الكاميرا فقط", text)
        self.assertIn("cam-7", text)

    def test_observations_from_another_camera_are_excluded_and_flagged(self):
        alert = make_alert(faceSummary={
            "enabled": True,
            "unknownIds": ["U-scope", "U-1"],
            "unknownDetails": [
                {"id": "U-scope", "cameraId": "cam-9", "firstSeenAt": "2026-09-29T11:59:30+00:00",
                 "lastSeenAt": "2026-09-29T12:00:10+00:00"},
                {"id": "U-1", "cameraId": "cam-7", "firstSeenAt": "2026-09-29T11:59:30+00:00",
                 "lastSeenAt": "2026-09-29T12:00:10+00:00"},
            ],
        })
        text = build_local_report(alert)
        self.assertIn("ملاحظات من كاميرا أخرى مستثناة من العد: 1", text)
        self.assertIn("خارج نطاق هذه الكاميرا — مستثناة من العد", text)
        self.assertIn("1 من أصل 4 صفوف مسجّلة", text)


class SourceLabels(_Case):
    def test_replay_label(self):
        self.assertIn("إعادة تشغيل", build_local_report(make_alert(source_type="demo_clip")))
        self.assertIn("إعادة تشغيل", build_local_report(make_alert(sourceKind="file")))

    def test_live_label(self):
        self.assertIn("بث مباشر (live)", build_local_report(make_alert(source_type="live_camera")))

    def test_unknown_source_is_explicit_not_assumed_live(self):
        text = build_local_report(make_alert())
        self.assertIn("غير مُتحقَّق (unverified)", text)
        self.assertIn("لا يُفترض أنه بث مباشر", text)


class UnknownsAndFaceAbsence(_Case):
    def test_no_face_frame_is_explicit_absence(self):
        text = build_local_report(make_alert())
        self.assertIn("لم يُعثر على إطار وجه صالح", text)
        self.assertIn("لا يذكر هذا التقرير هوية أي شخص", text)

    def test_face_absence_not_invented_when_empty_summary(self):
        text = build_local_report(make_alert(faceSummary={"enabled": False, "totalFaces": 0, "unknownIds": [], "unknownDetails": []}))
        self.assertIn("لم يُعثر على إطار وجه صالح", text)


class EvidenceFingerprints(_Case):
    def test_snapshot_hash_computed_from_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            snap = Path(tmp) / "snap.jpg"
            snap.write_bytes(b"abc")
            text = build_local_report(make_alert(thumbnailPath=str(snap)))
            self.assertIn("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", text)  # sha256(b"abc")
            self.assertIn("JPEG بجودة 85", text)
            self.assertIn("ليست أصلًا مرجعيًا", text)

    def test_chain_hashes_rendered_and_garbage_rejected(self):
        good = "a" * 64
        text = build_local_report(make_alert(), chain={
            "clipSha256": good, "reportSha256": "N/A", "snapshotSha256": "not-a-hash",
            "clipDurationSeconds": 8.5, "clipFrameCount": 170, "clipFps": 20.0,
            "recordType": "alert-receipt", "futureKey": {"nested": True},
        })
        self.assertIn(f"- مقطع الفيديو: SHA-256 = {good}", text)
        self.assertIn("مدة المقطع = 8.500 ثانية", text)
        self.assertNotIn("not-a-hash", text)
        self.assertNotIn("ملف التقرير", text)  # reportSha256 invalid -> no invented line

    def test_missing_clip_hash_stated_as_unavailable(self):
        text = build_local_report(make_alert())
        self.assertIn("غير متاح وقت الإنشاء", text)
        self.assertIn("بصمة مقطع الفيديو: غير متاحة وقت الإنشاء", text)


class ReportSizeGuards(_Case):
    def test_report_stays_within_ui_contract_limit_with_many_rows(self):
        rows = [
            {"id": f"U-{i:05d}", "firstSeenAt": "2026-09-29T11:59:30+00:00",
             "lastSeenAt": "2026-09-29T12:00:10+00:00", "durationFrames": 20, "hitStreak": 5}
            for i in range(4000)
        ]
        text = build_local_report(make_alert(faceSummary={
            "enabled": True, "unknownIds": [r["id"] for r in rows], "unknownDetails": rows,
        }))
        self.assertLessEqual(len(text), 100_000)
        self.assertIn("ملاحظة إضافية غير معروضة", text)  # omission is stated, not silent
        self.assertIn("4000", text)                      # counts still cover every row
        self.assertIn("ملاحظة U-00000", text)

    def test_many_labels_and_ids_are_capped_with_note(self):
        alert = make_alert(faceSummary={
            "enabled": True,
            "unknownIds": [f"U-{i}" for i in range(50)],
            "recognized": [{"personId": f"P-{i}"} for i in range(50)],
            "unknownDetails": [],
        })
        text = build_local_report(alert)
        self.assertIn("و 30 إضافية", text)  # 50 ids/labels shown 20 each
        self.assertLessEqual(len(text), 100_000)

    def test_hard_length_guard_truncates_with_visible_note(self):
        original = local_forensics._MAX_REPORT_CHARS
        local_forensics._MAX_REPORT_CHARS = 1500
        try:
            text = build_local_report(make_alert(faceSummary={
                "enabled": True,
                "unknownIds": [f"U-{i}" for i in range(60)],
                "unknownDetails": [
                    {"id": f"U-{i}", "firstSeenAt": "2026-09-29T11:59:30+00:00",
                     "lastSeenAt": "2026-09-29T12:00:10+00:00"} for i in range(60)
                ],
            }))
        finally:
            local_forensics._MAX_REPORT_CHARS = original
        self.assertLessEqual(len(text), 1500)
        self.assertTrue(text.endswith(local_forensics._TRUNCATION_NOTE))


class OfflineDeterminism(_Case):
    def test_zero_network_socket_blocked(self):
        def boom(*_args, **_kwargs):
            raise AssertionError("network access attempted by local report path")

        originals = (socket.socket, socket.create_connection, socket.getaddrinfo)
        socket.socket = boom  # type: ignore[assignment]
        socket.create_connection = boom  # type: ignore[assignment]
        socket.getaddrinfo = boom  # type: ignore[assignment]
        try:
            text = build_local_report(make_alert(thumbnailPath="Z:\\definitely\\missing.jpg"))
        finally:
            socket.socket, socket.create_connection, socket.getaddrinfo = originals
        self.assertIn("تقرير واقعة محلي", text)
        self.assertIn("دون اتصال بالإنترنت", text)

    def test_deterministic_identical_output(self):
        alert = make_alert(faceSummary={
            "enabled": True,
            "unknownIds": ["U-1", "U-1"],
            "unknownDetails": [{"id": "U-1", "firstSeenAt": "2026-09-29T11:59:30+00:00", "lastSeenAt": "2026-09-29T12:00:10+00:00"}],
        })
        first = build_local_report(alert)
        second = build_local_report(alert)

        def boom(*_args, **_kwargs):
            raise AssertionError("network access attempted")

        original_socket = socket.socket
        socket.socket = boom  # type: ignore[assignment]
        try:
            third = build_local_report(alert)
        finally:
            socket.socket = original_socket
        self.assertEqual(first, second)
        self.assertEqual(first, third)

    def test_module_imports_only_stdlib(self):
        import ast

        source = (Path(__file__).resolve().parent.parent / "backend" / "local_forensics.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        allowed = {"__future__", "hashlib", "math", "re", "datetime", "typing"}
        self.assertTrue(imported <= allowed, f"non-stdlib or unexpected imports: {imported - allowed}")


if __name__ == "__main__":
    unittest.main()
