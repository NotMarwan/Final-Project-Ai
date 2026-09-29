"""S-14 scoped tests: PDF incident report (F-25) facts/interpretation separation.

Run: py -m unittest tests.test_reporting_pdf -v
"""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import reporting  # noqa: E402
from reporting import build_incident_pdf  # noqa: E402

_DIA = re.compile(r"[ً-ْٰـ]")


def norm(text: str) -> str:
    return _DIA.sub("", text)


ALERT = {
    "id": "alert-pdf-1",
    "cameraId": "cam-7",
    "location": "cam-7",
    "timestamp": "12:00:00 UTC",
    "isoTime": "2026-09-29T12:00:00+00:00",
    "alertState": "CONFIRMED",
    "confidence": 87.5,
    "severity": "high",
    "type": "Weapon",
    "calibrationStatus": "unverified",
    "calibratedConfidence": None,
}


def build_captured(alert=None, report_text="", snapshot=False, report_source="model"):
    """Build a PDF while capturing every string that enters the flowable tree."""
    captured: list[str] = []
    orig_rtl, orig_para = reporting._rtl_paragraph, reporting.Paragraph

    def spy_rtl(text, style):
        captured.append(str(text))
        return orig_rtl(text, style)

    def spy_para(text, style):
        captured.append(str(text))
        return orig_para(text, style)

    reporting._rtl_paragraph = spy_rtl
    reporting.Paragraph = spy_para
    tmp = Path(tempfile.mkdtemp())
    snap_path = None
    if snapshot:
        snap_path = tmp / "snap.jpg"
        snap_path.write_bytes(b"jpegbytes")
    try:
        build_incident_pdf(alert or ALERT, report_text, snap_path, None, tmp / "out.pdf", report_source=report_source)
    finally:
        reporting._rtl_paragraph = orig_rtl
        reporting.Paragraph = orig_para
    return norm("\n".join(captured))


class PdfSectionDiscipline(unittest.TestCase):
    def test_model_text_is_labelled_interpretation_not_fact(self):
        joined = build_captured(report_text="Summary: a suspicious person was detected")
        self.assertIn(norm("تفسيرات النموذج — غير مُتحقَّق منها"), joined)
        self.assertIn(norm("نص النموذج — تفسير غير مُتحقَّق"), joined)
        self.assertIn(norm("حقيقة مثبتة ولا قراءة مباشرة للفيديو"), joined)

    def test_arabic_vlm_claim_text_is_labelled_interpretation(self):
        vlm_claim = "يظهر رجل يحمل سكينًا ويهدد شخصًا آخر داخل المتجر"
        joined = build_captured(report_text=vlm_claim)
        self.assertIn(norm("نص النموذج — تفسير غير مُتحقَّق"), joined)
        self.assertNotIn(norm("الملخص المحلي — حقائق مسجَّلة"), joined)
        # the claim itself is present, but inside the interpretation section that precedes it
        self.assertLess(joined.index(norm("نص النموذج — تفسير غير مُتحقَّق")), joined.index(norm("سكينًا")))

    def test_local_facts_text_stays_out_of_model_section(self):
        from local_forensics import build_local_report
        joined = build_captured(report_text=build_local_report(ALERT), report_source="local_facts")
        self.assertIn(norm("الملخص المحلي — حقائق مسجَّلة"), joined)
        self.assertNotIn(norm("نص النموذج — تفسير غير مُتحقَّق"), joined)

    def test_pending_report_text_reports_pending_state(self):
        joined = build_captured(report_text="Visual analysis is still pending.")
        self.assertIn(norm("لم يُنشئ نموذج تقريرًا نصيًا بعد"), joined)

    def test_sections_present_in_order(self):
        joined = build_captured(report_text="Summary: x")
        order = [joined.index(norm(h)) for h in (
            "الحقائق المسجلة", "بصمات الأدلة", "تفسيرات النموذج", "معلومات غير متاحة أو غير معروفة", "حدود التقرير",
        )]
        self.assertEqual(order, sorted(order))


class PdfFingerprintsAndFaces(unittest.TestCase):
    def test_missing_hashes_stated_absent(self):
        joined = build_captured(report_text="Summary: x")
        self.assertIn(norm("بصمة مقطع الفيديو: غير متاحة وقت إنشاء التقرير"), joined)
        self.assertIn(norm("لم يُعثر على ملف لقطة محفوظ"), joined)

    def test_snapshot_provenance_wording(self):
        joined = build_captured(report_text="Summary: x", snapshot=True)
        self.assertIn(norm("JPEG بجودة 85"), joined)
        self.assertIn(norm("ليست أصلًا مرجعيًا وليس إطار المقطع"), joined)

    def test_face_rows_deduped_and_stale_marked(self):
        alert = {**ALERT, "faceSummary": {
            "enabled": True,
            "unknownIds": ["U-1", "U-1"],
            "unknownDetails": [
                {"id": "U-1", "firstSeenAt": "2026-09-29T11:59:30+00:00", "lastSeenAt": "2026-09-29T12:00:10+00:00", "durationFrames": 20, "hitStreak": 5},
                {"id": "U-1", "firstSeenAt": "2026-09-29T11:59:30+00:00", "lastSeenAt": "2026-09-29T12:00:10+00:00", "durationFrames": 20, "hitStreak": 5},
                {"id": "U-old", "firstSeenAt": "2026-09-29T10:00:00+00:00", "lastSeenAt": "2026-09-29T10:05:00+00:00", "durationFrames": 2, "hitStreak": 1},
            ],
        }}
        joined = build_captured(alert=alert, report_text="Summary: x")
        self.assertEqual(joined.count("U-1: first="), 1)  # duplicate row rendered once
        self.assertIn(norm("قديمة — تنتهي قبل وقت الواقعة بأكثر من 300 ثانية"), joined)
        self.assertIn(norm("وليست هويات مؤكدة"), joined)


if __name__ == "__main__":
    unittest.main()
