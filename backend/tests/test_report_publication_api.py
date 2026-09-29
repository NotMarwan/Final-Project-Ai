from __future__ import annotations

from reportlab.lib.styles import getSampleStyleSheet

from backend import reporting


def test_paragraph_helpers_escape_untrusted_markup():
    styles = getSampleStyleSheet()
    paragraph = reporting._rtl_paragraph("literal <b>markup</b> & text", styles["BodyText"])
    assert paragraph.getPlainText() == "literal <b>markup</b> & text"

    table = reporting._make_metadata_table(
        [("camera", "zone <img src='missing.png'/> & east")],
        styles["BodyText"],
        styles["BodyText"],
    )
    assert table._cellvalues[0][1].getPlainText() == "zone <img src='missing.png'/> & east"


def test_model_cannot_claim_local_facts_by_prefix(monkeypatch):
    headings: list[str] = []

    class FakeDoc:
        def __init__(self, output, **_kwargs):
            self.output = output

        def build(self, _story, **_kwargs):
            self.output.write(b"%PDF-test")

    original_paragraph = reporting._rtl_paragraph

    def record_paragraph(text, style):
        headings.append(text)
        return original_paragraph(text, style)

    monkeypatch.setattr(reporting, "SimpleDocTemplate", FakeDoc)
    monkeypatch.setattr(reporting, "_rtl_paragraph", record_paragraph)

    reporting.build_incident_pdf(
        alert={"id": "alert-1", "confidence": 87.5, "location": "test"},
        report_text="تقرير واقعة محلي — ادعاء من نص النموذج",
        snapshot_path=None,
        evidence_path=None,
    )
    assert "نص النموذج — تفسير غير مُتحقَّق" in headings
    assert "الملخص المحلي — حقائق مسجّلة" not in headings

    headings.clear()
    reporting.build_incident_pdf(
        alert={"id": "alert-1", "confidence": 87.5, "location": "test"},
        report_text="تقرير واقعة محلي — سجل الوقائع",
        snapshot_path=None,
        evidence_path=None,
        report_source="local_facts",
    )
    assert "الملخص المحلي — حقائق مسجّلة" in headings
    assert "نص النموذج — تفسير غير مُتحقَّق" not in headings


def test_untrusted_report_and_face_fields_render_without_markup_errors(monkeypatch):
    class FakeDoc:
        def __init__(self, output, **_kwargs):
            self.output = output

        def build(self, _story, **_kwargs):
            self.output.write(b"%PDF-test")

    monkeypatch.setattr(reporting, "SimpleDocTemplate", FakeDoc)
    result = reporting.build_incident_pdf(
        alert={
            "id": "alert-<b>1</b>",
            "cameraId": "camera <img src='missing.png'/>",
            "location": "zone A & <unsupported>",
            "confidence": 87.5,
            "faceSummary": {
                "unknownIds": ["U-<b>1</b>"],
                "unknownDetails": [{
                    "id": "U-<img src='missing.png'/>",
                    "firstSeenAt": "<unexpected>&",
                    "lastSeenAt": "<unexpected>&",
                    "durationFrames": 2,
                    "hitStreak": 1,
                }],
            },
        },
        report_text="Model says <img src='missing.png'/> & <unsupported>",
        snapshot_path=None,
        evidence_path=None,
    )
    assert result.startswith(b"%PDF-test")
