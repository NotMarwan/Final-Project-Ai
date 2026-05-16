from __future__ import annotations

import hashlib
import os
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Mapping, Optional

from arabic_reshaper import reshape
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ARABIC_FONT_NAME = "AIArabic"
ARABIC_FONT_PATHS = [
    # Windows
    Path(r"C:\Windows\Fonts\DTNASKH0.TTF"),
    Path(r"C:\Windows\Fonts\tahoma.ttf"),
    Path(r"C:\Windows\Fonts\arial.ttf"),
    # Linux / Docker (DejaVu, Liberation, FreeSans — commonly available)
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
    Path("/usr/share/fonts/truetype/freefont/FreeSans.ttf"),
    Path("/usr/share/fonts/opentype/noto/NotoSans-Regular.ttf"),
    # macOS
    Path("/Library/Fonts/Arial.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
]


def _register_arabic_font() -> str:
    for font_path in ARABIC_FONT_PATHS:
        if font_path.exists():
            try:
                pdfmetrics.registerFont(TTFont(ARABIC_FONT_NAME, str(font_path)))
                return ARABIC_FONT_NAME
            except Exception:
                continue
    return "Helvetica"


FONT_NAME = _register_arabic_font()


def shape_arabic(text: str) -> str:
    if not text:
        return ""
    try:
        return get_display(reshape(text))
    except Exception:
        return text


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _sha256_file(path: Path | None) -> str:
    if not path or not path.exists():
        return "N/A"

    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _rtl_paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(shape_arabic(text), style)


def _make_metadata_table(rows: list[tuple[str, str]], label_style: ParagraphStyle, value_style: ParagraphStyle) -> Table:
    data = []
    for label, value in rows:
        data.append([
            _rtl_paragraph(label, label_style),
            Paragraph(_safe_str(value), value_style),
        ])

    table = Table(data, colWidths=[4.1 * cm, 10.5 * cm], hAlign="RIGHT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.whitesmoke),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#d7dce5")),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d7dce5")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def build_incident_pdf(
    alert: Mapping[str, Any],
    report_text: str,
    snapshot_path: Path | None,
    evidence_path: Path | None,
    output_path: Path | None = None,
) -> bytes:
    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=1.4 * cm,
        rightMargin=1.4 * cm,
        topMargin=1.3 * cm,
        bottomMargin=1.3 * cm,
        title=f"AI Sentinel Report {_safe_str(alert.get('id'))}",
        author="AI Sentinel",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "AISentinelTitle",
        parent=styles["Title"],
        fontName=FONT_NAME,
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0f172a"),
        alignment=TA_RIGHT,
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "AISentinelSub",
        parent=styles["Normal"],
        fontName=FONT_NAME,
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#475569"),
        alignment=TA_RIGHT,
        spaceAfter=10,
    )
    section_style = ParagraphStyle(
        "AISentinelSection",
        parent=styles["Heading2"],
        fontName=FONT_NAME,
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#b91c1c"),
        alignment=TA_RIGHT,
        spaceBefore=8,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "AISentinelBody",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=10.5,
        leading=15,
        textColor=colors.HexColor("#111827"),
        alignment=TA_RIGHT,
        rightIndent=0,
        spaceAfter=4,
    )
    body_left_style = ParagraphStyle(
        "AISentinelBodyLeft",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=9.5,
        leading=12,
        textColor=colors.HexColor("#111827"),
        alignment=TA_LEFT,
        spaceAfter=4,
    )
    label_style = ParagraphStyle(
        "AISentinelLabel",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=9.5,
        leading=12,
        textColor=colors.HexColor("#334155"),
        alignment=TA_RIGHT,
    )
    value_style = ParagraphStyle(
        "AISentinelValue",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=9.5,
        leading=12,
        textColor=colors.black,
        alignment=TA_LEFT,
    )

    alert_id = _safe_str(alert.get("id"), "unknown")
    report_text = _safe_str(report_text, "No forensic report was generated yet.")
    report_hash = _sha256_text(report_text)
    snapshot_hash = _sha256_file(snapshot_path)
    evidence_hash = _sha256_file(evidence_path)
    face_summary = alert.get("faceSummary")
    if not isinstance(face_summary, Mapping):
        face_summary = {}

    recognized = face_summary.get("recognized", [])
    if not isinstance(recognized, list):
        recognized = []

    unknown_ids = face_summary.get("unknownIds", [])
    if not isinstance(unknown_ids, list):
        unknown_ids = []

    unknown_details = face_summary.get("unknownDetails", [])
    if not isinstance(unknown_details, list):
        unknown_details = []

    recognized_labels: list[str] = []
    for item in recognized:
        if not isinstance(item, Mapping):
            continue
        label = _safe_str(item.get("label"), _safe_str(item.get("personId"), ""))
        if label:
            recognized_labels.append(label)

    unknown_label_join = ", ".join(str(x) for x in unknown_ids[:12]) or "N/A"
    recognized_label_join = ", ".join(recognized_labels[:8]) or "N/A"
    if len(unknown_ids) > 12:
        unknown_label_join += " ..."
    if len(recognized_labels) > 8:
        recognized_label_join += " ..."

    story: list[Any] = []
    story.append(_rtl_paragraph("تقرير جنائي آلي", title_style))
    story.append(_rtl_paragraph("AI Sentinel | Forensic Incident Report", subtitle_style))
    story.append(Spacer(1, 0.15 * cm))

    meta_rows = [
        ("رقم البلاغ", alert_id),
        ("نوع الحادث", _safe_str(alert.get("type"), "Incident")),
        ("درجة الخطورة", _safe_str(alert.get("severity"), "high").upper()),
        ("الكاميرا", _safe_str(alert.get("cameraId"), "unknown")),
        ("الموقع", _safe_str(alert.get("location"), "Unknown")),
        ("نسبة الثقة", f"{_safe_str(alert.get('confidence'), '0')}%"),
        ("الوقت", _safe_str(alert.get("timestamp"), "--:--:-- UTC")),
        ("وقت الإنشاء", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")),
        ("بصمة التقرير النصي", report_hash),
        ("بصمة اللقطة", snapshot_hash),
        ("بصمة ملف الفيديو", evidence_hash),
    ]
    meta_rows.extend(
        [
            ("Face Intel Enabled", "Yes" if face_summary.get("enabled") else "No"),
            ("Faces In Event", _safe_str(face_summary.get("totalFaces"), "0")),
            ("Recognized Count", _safe_str(face_summary.get("recognizedCount"), _safe_str(len(recognized), "0"))),
            ("Unknown Count", _safe_str(face_summary.get("unknownCount"), _safe_str(len(unknown_ids), "0"))),
            ("Recognized Labels", recognized_label_join),
            ("Unknown IDs", unknown_label_join),
        ]
    )

    story.append(_make_metadata_table(meta_rows, label_style, value_style))
    story.append(Spacer(1, 0.35 * cm))

    story.append(_rtl_paragraph("الملخص التحليلي", section_style))
    for chunk in report_text.splitlines() or [report_text]:
        if chunk.strip():
            story.append(_rtl_paragraph(chunk.strip(), body_style))
    story.append(Spacer(1, 0.2 * cm))

    if snapshot_path and snapshot_path.exists():
        story.append(_rtl_paragraph("لقطة دليل مرئي", section_style))
        try:
            image = Image(str(snapshot_path))
            image._restrictSize(16 * cm, 9 * cm)
            story.append(image)
        except Exception:
            story.append(_rtl_paragraph("تعذر تضمين صورة اللقطة داخل التقرير.", body_style))
        story.append(Spacer(1, 0.2 * cm))

    if unknown_details:
        story.append(_rtl_paragraph("Face Timeline (Unknown IDs)", section_style))
        for item in unknown_details[:20]:
            if not isinstance(item, Mapping):
                continue
            line = (
                f"{_safe_str(item.get('id'), 'U-?')}: "
                f"first={_safe_str(item.get('firstSeenAt'), 'N/A')}, "
                f"last={_safe_str(item.get('lastSeenAt'), 'N/A')}, "
                f"frames={_safe_str(item.get('durationFrames'), '0')}, "
                f"hits={_safe_str(item.get('hitStreak'), '0')}"
            )
            story.append(Paragraph(line, body_left_style))
        story.append(Spacer(1, 0.2 * cm))

    notes_rows = [
        ("حالة الأرشفة", "Evidence clip attached" if evidence_path and evidence_path.exists() else "Evidence clip missing"),
        ("ملاحظات", "This report was generated automatically from the AI Sentinel pipeline."),
    ]
    story.append(_rtl_paragraph("ملاحظات الأمان", section_style))
    story.append(_make_metadata_table(notes_rows, label_style, value_style))

    def _draw_footer(canvas, doc_obj):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#e2e8f0"))
        canvas.line(doc_obj.leftMargin, 1.1 * cm, A4[0] - doc_obj.rightMargin, 1.1 * cm)
        canvas.setFont(FONT_NAME, 8)
        footer_left = f"AI Sentinel | {alert_id}"
        footer_right = f"Page {canvas.getPageNumber()}"
        canvas.drawString(doc_obj.leftMargin, 0.6 * cm, footer_left)
        canvas.drawRightString(A4[0] - doc_obj.rightMargin, 0.6 * cm, footer_right)
        canvas.restoreState()

    doc.build(story, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    pdf_bytes = output.getvalue()

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(pdf_bytes)

    return pdf_bytes
