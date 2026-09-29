from __future__ import annotations

import hashlib
import math
from xml.sax.saxutils import escape
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Mapping

from arabic_reshaper import reshape
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
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

# Same rule as backend/local_forensics.py (single source: local_forensics constant
# is imported below when available; this fallback keeps the module importable alone).
_STALE_BEFORE_EVENT_SECONDS = 300

try:  # package import (backend.reporting)
    from .local_forensics import _parse_iso as _lf_parse_iso, _fmt_utc as _lf_fmt_utc
    from .local_forensics import _STALE_BEFORE_EVENT_SECONDS as _STALE_SECONDS
except ImportError:  # flat import (reporting)
    try:
        from local_forensics import _parse_iso as _lf_parse_iso, _fmt_utc as _lf_fmt_utc
        from local_forensics import _STALE_BEFORE_EVENT_SECONDS as _STALE_SECONDS
    except ImportError:  # local_forensics absent: degrade to no stale marking
        _lf_parse_iso = None
        _lf_fmt_utc = None
        _STALE_SECONDS = _STALE_BEFORE_EVENT_SECONDS

# Report provenance is passed by the caller. Report content is untrusted text;
# it cannot establish that it contains local facts by claiming a prefix.
_PENDING_REPORT_TEXT = "Visual analysis is still pending."


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
    return Paragraph(escape(shape_arabic(text)), style)


def _make_metadata_table(rows: list[tuple[str, str]], label_style: ParagraphStyle, value_style: ParagraphStyle) -> Table:
    data = []
    for label, value in rows:
        data.append([
            _rtl_paragraph(label, label_style),
            Paragraph(escape(_safe_str(value)), value_style),
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
    report_source: str = "model",
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
    raw_report_text = _safe_str(report_text)
    is_local_facts = report_source == "local_facts"
    report_hash = _sha256_text(raw_report_text) if raw_report_text else "N/A"
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

    # Dedupe: one face id is one observation, however many rows carry it.
    seen_ids: dict[str, None] = {}
    for item in unknown_ids:
        text = _safe_str(item, "")[:40]
        if text:
            seen_ids.setdefault(text, None)
    deduped_unknown_ids = list(seen_ids)

    recognized_labels: list[str] = []
    for item in recognized:
        if not isinstance(item, Mapping):
            continue
        label = _safe_str(item.get("label"), _safe_str(item.get("personId"), ""))
        if label:
            recognized_labels.append(label)

    unknown_label_join = ", ".join(deduped_unknown_ids[:12]) or "N/A"
    recognized_label_join = ", ".join(recognized_labels[:8]) or "N/A"
    if len(deduped_unknown_ids) > 12:
        unknown_label_join += " ..."
    if len(recognized_labels) > 8:
        recognized_label_join += " ..."

    story: list[Any] = []
    story.append(_rtl_paragraph("تقرير جنائي آلي", title_style))
    story.append(_rtl_paragraph("AI Sentinel | Forensic Incident Report", subtitle_style))
    story.append(Spacer(1, 0.15 * cm))

    # ---------------- Facts (recorded) ----------------
    story.append(_rtl_paragraph("الحقائق المسجلة", section_style))
    meta_rows = [
        ("رقم البلاغ", alert_id),
        ("الكاميرا", _safe_str(alert.get("cameraId"), "unknown")),
        ("الموقع", _safe_str(alert.get("location"), "Unknown")),
        ("وقت الواقعة", _safe_str(alert.get("timestamp"), "--:--:-- UTC")),
        ("وقت إنشاء التقرير", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")),
        ("حالة القرار المسجّلة", _safe_str(alert.get("alertState", alert.get("alert_state")), "غير مُسجَّلة")),
    ]
    story.append(_make_metadata_table(meta_rows, label_style, value_style))
    story.append(Spacer(1, 0.3 * cm))

    # ---------------- Evidence fingerprints (C-C1 semantics) ----------------
    story.append(_rtl_paragraph("بصمات الأدلة", section_style))
    fingerprint_rows = [
        ("لقطة الحادثة (snapshot)", snapshot_hash if snapshot_hash != "N/A" else "غير متاح"),
        ("مقطع الفيديو (clip)", evidence_hash if evidence_hash != "N/A" else "غير متاح وقت الإنشاء"),
        ("نص التقرير المضمَّن", report_hash),
    ]
    story.append(_make_metadata_table(fingerprint_rows, label_style, value_style))
    story.append(_rtl_paragraph(
        "لقطة الحادثة: JPEG بجودة 85 — إعادة ترميز ضائرة (lossy) لإطار مُفكَّك بدقة المصدر بعد رسم التعليقات "
        "التوضيحية؛ ليست أصلًا مرجعيًا وليس إطار المقطع. البصمات محسوبة من الملفات المحفوظة، "
        "وتُقارن بسجل الأدلة (سلسلة الهاش) عند المراجعة.",
        body_style,
    ))
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

    # ---------------- Model interpretations (never facts) ----------------
    story.append(_rtl_paragraph("تفسيرات النموذج — غير مُتحقَّق منها", section_style))
    calibration_status = _safe_str(alert.get("calibrationStatus"), "")
    calibration_note = (
        "حالة المعايرة المسجّلة: معايرة مطبَّقة (calibrated)."
        if calibration_status == "calibrated" and alert.get("calibratedConfidence") is not None
        else "لا توجد معايرة مسجَّلة للنموذج — القيم أدناه تقديرات غير مُتحقَّق منها."
    )
    story.append(_rtl_paragraph(
        "تحذير: ما يلي تقديرات وتسميات مخرجات نماذج تعلّمي آلي، وليست حقائق مؤكدة أو مشاهدات مباشرة. "
        + calibration_note,
        body_style,
    ))
    confidence = alert.get("confidence")
    confidence_text = _safe_str(confidence, "غير مُسجَّلة")
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool) and math.isfinite(float(confidence)):
        confidence_text = f"{float(confidence):.1f}%"
    interp_rows = [
        ("نوع الحادث المصنَّف آليًا", _safe_str(alert.get("type"), "Incident")),
        ("درجة الخطورة (قرار آلي)", _safe_str(alert.get("severity"), "high").upper()),
        ("نسبة الثقة (تقدير نموذج)", confidence_text),
    ]
    story.append(_make_metadata_table(interp_rows, label_style, value_style))

    if raw_report_text:
        if is_local_facts:
            story.append(_rtl_paragraph("الملخص المحلي — حقائق مسجّلة", section_style))
        elif raw_report_text.strip() == _PENDING_REPORT_TEXT:
            story.append(_rtl_paragraph("حالة التقرير النصي", section_style))
            story.append(_rtl_paragraph("لم يُنشئ نموذج تقريرًا نصيًا بعد لهذه الواقعة.", body_style))
            raw_report_text = ""
        else:
            story.append(_rtl_paragraph("نص النموذج — تفسير غير مُتحقَّق", section_style))
            story.append(_rtl_paragraph(
                "النص أدناه صياغة آلية من بيانات الواقعة؛ ليس حقيقة مثبتة ولا قراءة مباشرة للفيديو.",
                body_style,
            ))
        for chunk in raw_report_text.splitlines() or [raw_report_text]:
            if chunk.strip():
                story.append(_rtl_paragraph(chunk.strip(), body_style))
        story.append(Spacer(1, 0.2 * cm))

    if unknown_details or deduped_unknown_ids or recognized_labels:
        story.append(_rtl_paragraph("ملخص الوجه (مخرجات نموذج — ليست هويات مؤكدة)", section_style))
        story.append(_rtl_paragraph(
            f"Recognized Labels: {recognized_label_join} — Unknown IDs: {unknown_label_join}. "
            "المعرّفات أعلاه مخرجات نموذج تتبع الوجوه، تُحتسب كل معرّف مرة واحدة، وليست هويات مؤكدة.",
            body_left_style,
        ))
        event_time = _lf_parse_iso(alert.get("isoTime")) if _lf_parse_iso else None
        seen_detail_ids: dict[str, None] = {}
        for item in unknown_details[:40]:
            if not isinstance(item, Mapping):
                continue
            row_id = _safe_str(item.get("id"), "U-?")
            if row_id in seen_detail_ids:
                continue  # duplicate rows count once
            seen_detail_ids[row_id] = None
            first = _lf_parse_iso(item.get("firstSeenAt")) if _lf_parse_iso else None
            last = _lf_parse_iso(item.get("lastSeenAt")) if _lf_parse_iso else None
            stale = bool(event_time is not None and last is not None
                         and (event_time - last).total_seconds() > _STALE_SECONDS)
            line = (
                f"{row_id}: "
                f"first={_lf_fmt_utc(first) if (first and _lf_fmt_utc) else _safe_str(item.get('firstSeenAt'), 'N/A')}, "
                f"last={_lf_fmt_utc(last) if (last and _lf_fmt_utc) else _safe_str(item.get('lastSeenAt'), 'N/A')}, "
                f"frames={_safe_str(item.get('durationFrames'), '0')}, "
                f"hits={_safe_str(item.get('hitStreak'), '0')}"
            )
            if stale:
                line += f" [قديمة — تنتهي قبل وقت الواقعة بأكثر من {_STALE_SECONDS} ثانية؛ مستثناة من العد]"
            story.append(Paragraph(escape(line), body_left_style))
        story.append(Spacer(1, 0.2 * cm))

    # ---------------- Unknowns (explicit absences) ----------------
    story.append(_rtl_paragraph("معلومات غير متاحة أو غير معروفة", section_style))
    unknown_lines: list[str] = []
    if snapshot_hash == "N/A":
        unknown_lines.append("بصمة لقطة الحادثة: غير متاحة — لم يُعثر على ملف لقطة محفوظ.")
    if evidence_hash == "N/A":
        unknown_lines.append("بصمة مقطع الفيديو: غير متاحة وقت إنشاء التقرير.")
    if alert.get("calibratedConfidence") is None:
        unknown_lines.append("الاحتمال بعد المعايرة (calibratedConfidence): لم يُسجَّل.")
    if not deduped_unknown_ids and not recognized_labels and not unknown_details:
        unknown_lines.append("الوجوه: لم يُعثر على إطار وجه صالح ضمن البيانات المسجّلة؛ لا يذكر هذا التقرير هوية أي شخص.")
    if not unknown_lines:
        unknown_lines.append("لا توجد بيانات ناقصة إضافية مسجَّلة لهذه الواقعة.")
    for line in unknown_lines:
        story.append(_rtl_paragraph(f"- {line}", body_style))
    story.append(Spacer(1, 0.2 * cm))

    # ---------------- Limitations ----------------
    story.append(_rtl_paragraph("حدود التقرير", section_style))
    notes_rows = [
        ("حالة الأرشفة", "Evidence clip attached" if evidence_path and evidence_path.exists() else "Evidence clip missing"),
        ("حدود المحتوى", "لم يُجرَ تحليل لغوي بصري للصورة ضمن التوليد التلقائي. لا يثبت التقرير هوية الأشخاص أو نيتهم أو وقوع جريمة؛ التأكيد يتطلب مراجعة المشغّل للأدلة."),
    ]
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
