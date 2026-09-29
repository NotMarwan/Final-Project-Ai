"""Offline Arabic evidence summary (F-28): facts vs interpretation vs unknowns.

Discipline (binding for S-14):
- RECORDED FACTS: only what the system stored (ids, times, counts, hashes, durations).
- MODEL INTERPRETATIONS: model scores/labels, explicitly labelled unverified where no
  calibration is recorded. Never presented as facts.
- UNKNOWNS: anything absent (null score, no usable face frame, missing hash) is stated
  as explicitly absent — never invented, never defaulted to zero.

This module performs no image analysis and contacts no network. `build_local_report`
is a pure deterministic function of its inputs. The optional ``chain`` argument is the
evidence ledger receipt (ui-contract C-4a shape, WT-24 additions tolerated but not
required) and is only read for per-file SHA-256 fingerprints (C-C1 semantics).
"""
from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

REPORT_MODE = "local-evidence-summary"  # wire literal, ui-contract C-4b
UNAVAILABLE = "غير متاح"
NOT_RECORDED = "لم تُسجَّل"

_REPORT_HEADER = "تقرير واقعة محلي — ملخص بيانات النظام"
_FACTS_HEADER = "أولاً: الحقائق المسجلة"
_INTERP_HEADER = "ثانياً: تفسيرات النموذج — غير مُتحقَّق منها"
_UNKNOWN_HEADER = "ثالثاً: معلومات غير متاحة أو غير معروفة"
_LIMITS_HEADER = "حدود التقرير"

# An observation that ends before the event time by more than this window is stale
# evidence for this incident. The rule is stated verbatim in the report text so the
# operator can audit it; it is never applied silently.
_STALE_BEFORE_EVENT_SECONDS = 300

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")

# Display caps: counts always cover every recorded row, but only this many rows are
# rendered, with an explicit "… and N more" note. The final report also honours the
# UI contract limit (lib/local-report.ts rejects reports longer than 100_000 chars).
_DISPLAY_DETAIL_ROWS = 50
_DISPLAY_LABELS = 20
_MAX_REPORT_CHARS = 100_000
_TRUNCATION_NOTE = "تم اختصار التقرير عند حد الطول المسموح؛ العدد الكامل مُحتسب أعلاه وسجل الأدلة يحتوي التفاصيل."


def _safe_text(value: Any, limit: int = 120) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:limit]


def _number(value: Any, digits: int = 2) -> Optional[str]:
    """Format a recorded measurement. Absent/invalid stays absent; observed zero stays zero."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return f"{result:.{digits}f}"


def _int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sha256_or_none(value: Any) -> Optional[str]:
    if isinstance(value, str) and _SHA256_RE.fullmatch(value.strip()):
        return value.strip().lower()
    return None  # legacy "N/A", absent or malformed -> absent, never invented


def _sha256_file(path_text: Optional[str]) -> Optional[str]:
    if not path_text or not isinstance(path_text, str):
        return None
    try:
        digest = hashlib.sha256()
        with open(path_text, "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _parse_iso(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _fmt_utc(moment: Optional[datetime]) -> Optional[str]:
    if moment is None:
        return None
    return moment.strftime("%Y-%m-%d %H:%M:%S UTC")


def _unique(values: Any) -> list[str]:
    """Dedupe while preserving first-seen order; every id is counted once."""
    seen: dict[str, None] = {}
    if isinstance(values, list):
        for item in values:
            text = _safe_text(item)
            if text is not None:
                seen.setdefault(text, None)
    return list(seen)


def _source_mode(alert: Mapping[str, Any]) -> str:
    """Map recorded source hints onto the product vocabulary (lib/live-visual-state.ts):
    replay | live | unverified. Absent hints stay unverified — never assumed live."""
    source_type = _safe_text(alert.get("source_type"))
    source_kind = _safe_text(alert.get("sourceKind"))
    if source_type == "demo_clip" or source_kind == "file":
        return "replay"
    if (alert.get("demo_mode") is True or alert.get("demoMode") is True
            or alert.get("isDemo") is True or alert.get("externalPlayback") is True):
        return "replay"
    if source_type == "live_camera" or source_kind == "live":
        return "live"
    return "unverified"


_SOURCE_LABELS = {
    "replay": "إعادة تشغيل / مقطع تجريبي (replay) — مسجَّل من ملف",
    "live": "بث مباشر (live)",
    "unverified": "غير مُتحقَّق (unverified) — نوع المصدر غير مُسجَّل؛ لا يُفترض أنه بث مباشر",
}


def _face_block(alert: Mapping[str, Any]) -> dict[str, Any]:
    """Collect face-model observations: deduped, window-scoped, stale-marked."""
    face_summary = alert.get("faceSummary")
    if not isinstance(face_summary, Mapping):
        face_summary = {}
    event_time = _parse_iso(alert.get("isoTime"))

    recognized = face_summary.get("recognized") if isinstance(face_summary.get("recognized"), list) else []
    unknown_ids = _unique(face_summary.get("unknownIds"))
    details_raw = face_summary.get("unknownDetails") if isinstance(face_summary.get("unknownDetails"), list) else []

    detail_rows: list[tuple[str, str, str]] = []  # (id, span_text, flags)
    detail_rows_omitted = 0
    detail_ids: list[str] = []
    stale_ids: set[str] = set()
    out_of_scope_ids: set[str] = set()
    alert_camera = _safe_text(alert.get("cameraId"), 60)
    stale_count = 0
    included_times: list[datetime] = []
    for item in details_raw:
        if not isinstance(item, Mapping):
            continue
        item_id = _safe_text(item.get("id"), 40) or "U-?"
        if item_id in detail_ids:
            continue  # duplicate event rows count once
        detail_ids.append(item_id)
        row_camera = _safe_text(item.get("cameraId"), 60)
        off_scope = bool(row_camera and alert_camera and row_camera != alert_camera)
        if off_scope:
            out_of_scope_ids.add(item_id)
        first = _parse_iso(item.get("firstSeenAt"))
        last = _parse_iso(item.get("lastSeenAt"))
        frames = _int(item.get("durationFrames"))
        hits = _int(item.get("hitStreak"))
        is_stale = bool(
            event_time is not None and last is not None
            and (event_time - last) > timedelta(seconds=_STALE_BEFORE_EVENT_SECONDS)
        )
        flags: list[str] = []
        if off_scope:
            flags.append("خارج نطاق هذه الكاميرا — مستثناة من العد")
        elif is_stale:
            flags.append("قديمة — مستثناة من العد")
            stale_count += 1
            stale_ids.add(item_id)
        else:
            if first is not None:
                included_times.append(first)
            if last is not None:
                included_times.append(last)
        span = f"{_fmt_utc(first) or UNAVAILABLE} ← {_fmt_utc(last) or UNAVAILABLE}"
        extras = []
        if frames is not None:
            extras.append(f"frames={frames}")
        if hits is not None:
            extras.append(f"hits={hits}")
        if extras:
            span += " (" + ", ".join(extras) + ")"
        if flags:
            span += " [" + "؛ ".join(flags) + "]"
        if len(detail_rows) < _DISPLAY_DETAIL_ROWS:
            detail_rows.append((item_id, span, ""))
        else:
            detail_rows_omitted += 1

    recognized_labels: list[str] = []
    for item in recognized:
        if isinstance(item, Mapping):
            label = _safe_text(item.get("label")) or _safe_text(item.get("personId"))
            if label:
                recognized_labels.append(label)
    recognized_labels = _unique(recognized_labels)

    total_faces = _int(face_summary.get("totalFaces"))
    # One id in both unknownIds and unknownDetails is a single observation; stale
    # observations are recorded but explicitly excluded from the counted total.
    unique_unknown_ids = _unique(unknown_ids + detail_ids)
    excluded_ids = stale_ids | out_of_scope_ids
    counted_ids = _unique([i for i in unknown_ids + detail_ids if i not in excluded_ids])
    raw_rows = (
        (len(details_raw) if isinstance(details_raw, list) else 0)
        + (len(face_summary.get("unknownIds")) if isinstance(face_summary.get("unknownIds"), list) else 0)
        + len(recognized)
    )
    counted = len(counted_ids) + len(recognized_labels)
    return {
        "enabled": bool(face_summary.get("enabled")),
        "total_faces": total_faces,
        "unknown_ids": unique_unknown_ids,
        "detail_rows": detail_rows,
        "detail_rows_omitted": detail_rows_omitted,
        "recognized_labels": recognized_labels,
        "stale_count": stale_count,
        "out_of_scope_count": len(out_of_scope_ids),
        "counted": counted,
        "raw_rows": raw_rows,
        "included_times": included_times,
    }


def _fingerprint_lines(alert: Mapping[str, Any], chain: Optional[Mapping[str, Any]]) -> list[str]:
    """Per-file SHA-256 fingerprints (C-C1). Missing files/hashes are stated as missing."""
    receipt = chain if isinstance(chain, Mapping) else {}
    lines = ["بصمات الأدلة (بصمة SHA-256 لكل ملف مُشار إليه):"]

    snapshot_hash = _sha256_file(_safe_text(alert.get("thumbnailPath"), 4096))
    snapshot_origin = "محسوبة من الملف المحفوظ على القرص"
    if snapshot_hash is None:
        snapshot_hash = _sha256_or_none(receipt.get("snapshotSha256"))
        snapshot_origin = "من سجل الأدلة" if snapshot_hash else None
    if snapshot_hash:
        lines.append(
            f"- لقطة الحادثة: SHA-256 = {snapshot_hash} ({snapshot_origin}) — "
            "JPEG بجودة 85، إعادة ترميز ضائرة (lossy) لإطار مُفكَّك بدقة المصدر بعد رسم التعليقات التوضيحية؛ "
            "ليست أصلًا مرجعيًا وليس إطار المقطع."
        )
    else:
        lines.append(f"- لقطة الحادثة: {UNAVAILABLE} — لم يُعثر على ملف لقطة محفوظ أو بصمة صحيحة.")

    clip_hash = _sha256_or_none(receipt.get("clipSha256"))
    if clip_hash:
        lines.append(f"- مقطع الفيديو: SHA-256 = {clip_hash} (من سجل الأدلة).")
    else:
        lines.append("- مقطع الفيديو: غير متاح وقت الإنشاء (يُسجَّل لاحقًا في سجل الأدلة بعد اكتمال الترميز).")

    report_hash = _sha256_or_none(receipt.get("reportSha256"))
    if report_hash:
        lines.append(f"- ملف التقرير: SHA-256 = {report_hash} (من سجل الأدلة).")

    clip_meta: list[str] = []
    duration = _number(receipt.get("clipDurationSeconds"), 3)
    if duration is not None:
        clip_meta.append(f"مدة المقطع = {duration} ثانية")
    frames = _int(receipt.get("clipFrameCount"))
    if frames is not None:
        clip_meta.append(f"عدد الإطارات = {frames}")
    fps = _number(receipt.get("clipFps"), 3)
    if fps is not None:
        clip_meta.append(f"معدل الإطارات = {fps}")
    if clip_meta:
        lines.append("- بيانات المقطع المسجّلة: " + "، ".join(clip_meta) + ".")
    return lines


def build_local_report(alert: Any, chain: Optional[Mapping[str, Any]] = None) -> str:
    """Build the deterministic offline Arabic summary of one incident record.

    Reports only recorded facts, labels model output as unverified interpretation and
    states every absence explicitly. No image analysis, no network, no wall clock:
    identical inputs always produce an identical report."""
    data: Mapping[str, Any] = alert if isinstance(alert, Mapping) else {}

    alert_id = _safe_text(data.get("id")) or UNAVAILABLE
    camera_id = _safe_text(data.get("cameraId")) or UNAVAILABLE
    recorded_time = _safe_text(data.get("isoTime")) or _safe_text(data.get("timestamp")) or UNAVAILABLE
    alert_state = _safe_text(data.get("alertState") or data.get("alert_state"), 40) or UNAVAILABLE
    confirm_rule = _safe_text(data.get("confirmRule"), 60)
    person_count = _int(data.get("personCount"))
    source_mode = _source_mode(data)

    face = _face_block(data)

    # Incident window: event time plus every included observation timestamp.
    window_times: list[datetime] = list(face["included_times"])
    event_time = _parse_iso(data.get("isoTime"))
    if event_time is not None:
        window_times.append(event_time)
    window_line = UNAVAILABLE
    if window_times:
        window_line = f"{_fmt_utc(min(window_times))} ← {_fmt_utc(max(window_times))}"

    facts: list[str] = [_FACTS_HEADER]
    facts.append(f"معرّف الواقعة: {alert_id}")
    facts.append(
        f"الكاميرا ونطاق التقرير: {camera_id} — النطاق: هذه الكاميرا فقط؛ "
        "لا تُنسب أحداث أو مشاهدات من كاميرات أخرى إلى هذه الواقعة."
    )
    facts.append(f"وقت التسجيل (UTC): {recorded_time}")
    facts.append(f"نوع المصدر المسجّل: {_SOURCE_LABELS[source_mode]}")
    facts.append(f"حالة القرار المسجّلة: {alert_state}")
    if confirm_rule:
        facts.append(f"قاعدة التأكيد المسجّلة: {confirm_rule}")
    facts.append(f"عدد الأشخاص المسجّل: {person_count if person_count is not None else NOT_RECORDED}")
    facts.append(f"النافذة الزمنية للمحتوى المحتسب (UTC): {window_line}")
    facts.append(
        "الملاحظات المحتسبة (بدون تكرار وبعد استثناء القديمة): "
        f"{face['counted']} من أصل {face['raw_rows']} صفوف مسجّلة (يُحتسب كل معرّف مرة واحدة)."
    )
    if face["stale_count"]:
        facts.append(
            f"ملاحظات قديمة مستثناة من العد: {face['stale_count']} — "
            f"القاعدة المطبَّقة: أي ملاحظة تنتهي قبل وقت الواقعة بأكثر من {_STALE_BEFORE_EVENT_SECONDS} ثانية تُعتبر قديمة."
        )
    if face.get("out_of_scope_count"):
        facts.append(
            f"ملاحظات من كاميرا أخرى مستثناة من العد: {face['out_of_scope_count']} — "
            "النطاق: هذه الكاميرا فقط."
        )
    facts.append(
        "طبيعة القيم: القيم المسجّلة هي قيم لحظة التسجيل وليست قراءات حالية للحظة قراءة التقرير."
    )
    facts.extend(_fingerprint_lines(data, chain))
    facts.append(
        "المصدر: حقول الإنذار المسجلة محليًا؛ لا يتطلب هذا الملخص اتصالًا بالإنترنت أو أي خدمة خارجية."
    )

    calibration_status = _safe_text(data.get("calibrationStatus"), 40)
    calibrated = _number(data.get("calibratedConfidence"), 2)
    if calibration_status == "calibrated" and calibrated is not None:
        calibration_note = f"معايرة مسجّلة (calibrated) — الاحتمال المعاير مُتاح أدناه."
    else:
        calibration_note = (
            "لا توجد معايرة مسجّلة للنموذج (calibrationStatus غير مؤكد) — "
            "جميع القيم أدناه تقديرات غير مُتحقَّق منها."
        )

    interp: list[str] = [_INTERP_HEADER]
    interp.append(
        "تحذير: ما يلي مخرجات نماذج تعلّمي آلي (تقديرات وتسميات)، وليست حقائق مؤكدة أو مشاهدات مباشرة. "
        + calibration_note
    )
    for label, key, digits in (
        ("درجة الثقة (confidence)", "confidence", 1),
        ("الثقة الخام للنموذج (rawModelConfidence)", "rawModelConfidence", 4),
        ("درجة الاندماج (fusionScore)", "fusionScore", 4),
        ("درجة الحركة (motionScore)", "motionScore", 2),
        ("إشارة السلاح (weaponScore)", "weaponScore", 1),
    ):
        value = _number(data.get(key), digits)
        interp.append(f"- {label}: {value if value is not None else NOT_RECORDED}")
    interp.append(
        f"- الاحتمال بعد المعايرة (calibratedConfidence): {calibrated if calibrated is not None else NOT_RECORDED}"
    )
    threat_type = _safe_text(data.get("threatType")) or _safe_text(data.get("type"), 40)
    interp.append(f"- تصنيف التهديد المصنَّف آليًا (threatType/type): {threat_type if threat_type else NOT_RECORDED}")
    weapon_labels = _unique(data.get("weaponLabels"))
    interp.append(
        "- التسميات المصنَّفة آليًا (weaponLabels): "
        + (", ".join(weapon_labels) if weapon_labels else NOT_RECORDED)
        + " — تسميات نموذجية، لا تُحتسب كوقائع."
    )
    if face["total_faces"] or face["unknown_ids"] or face["recognized_labels"] or face["detail_rows"]:
        interp.append("ملخص الوجه (مخرجات نموذج تتبع الوجوه — ليست هويات مؤكدة):")
        if face["unknown_ids"]:
            shown = face["unknown_ids"][:_DISPLAY_LABELS]
            extra = len(face["unknown_ids"]) - len(shown)
            interp.append(
                "- معرّفات وجوه غير معروفة (مُحتسبة مرة واحدة): " + ", ".join(shown)
                + (f" … و {extra} إضافية" if extra else "")
            )
        if face["recognized_labels"]:
            shown = face["recognized_labels"][:_DISPLAY_LABELS]
            extra = len(face["recognized_labels"]) - len(shown)
            interp.append(
                "- تسميات وجوه معروفة (تصنيف نموذجي): " + ", ".join(shown)
                + (f" … و {extra} إضافية" if extra else "")
            )
        for item_id, span, _flags in face["detail_rows"]:
            interp.append(f"- ملاحظة {item_id}: {span}")
        if face["detail_rows_omitted"]:
            interp.append(
                f"- … و {face['detail_rows_omitted']} ملاحظة إضافية غير معروضة (العدد مُحتسب كاملًا أعلاه)."
            )

    unknowns: list[str] = [_UNKNOWN_HEADER]
    if calibrated is None:
        unknowns.append("- الاحتمال بعد المعايرة: لم يُسجَّل في بيانات الواقعة (null) — لا يُقدَّر ولا يُخمَّن.")
    for label, key in (
        ("درجة الثقة", "confidence"),
        ("درجة الاندماج", "fusionScore"),
        ("درجة الحركة", "motionScore"),
        ("إشارة السلاح", "weaponScore"),
        ("زمن إنذار التنبيه (alertLatencyMs)", "alertLatencyMs"),
    ):
        if _number(data.get(key), 4) is None:
            unknowns.append(f"- {label}: {NOT_RECORDED} في بيانات الواقعة.")
    if source_mode == "unverified":
        unknowns.append("- نوع المصدر (بث مباشر مقابل إعادة تشغيل): غير مُسجَّل — لا يُفترض أنه بث مباشر.")
    if not face["unknown_ids"] and not face["recognized_labels"] and not face["detail_rows"]:
        unknowns.append(
            "- الوجوه: لم يُعثر على إطار وجه صالح ضمن البيانات المسجلة لهذه الواقعة؛ "
            "لا يذكر هذا التقرير هوية أي شخص ولا يخمّن وجود أشخاص."
        )
    if _sha256_or_none((chain if isinstance(chain, Mapping) else {}).get("clipSha256")) is None:
        unknowns.append("- بصمة مقطع الفيديو: غير متاحة وقت الإنشاء.")

    limits: list[str] = [_LIMITS_HEADER]
    limits.append(
        "لم يُجرَ تحليل لغوي بصري للصورة ضمن هذا الملخص. لا يثبت الملخص هوية الأشخاص أو نيتهم أو وقوع جريمة. "
        "يتطلب التأكيد مراجعة المقطع والأدلة بواسطة المشغّل."
    )

    text = "\n".join([_REPORT_HEADER,
                      "الوضع: تحليل محلي مستقل — دون اتصال بالإنترنت أو أي خدمة خارجية.",
                      "طبيعة التقرير: يسرد ما سجّله النظام فقط (حقائق مسجلة)، ويعرض مخرجات النماذج موسومةً بأنها "
                      "تفسير غير مُتحقَّق، ويذكر بوضوح كل ما هو غير متاح. لم يُجرَ أي تحليل للصور ضمن هذا التقرير.",
                      ""] + facts + [""] + interp + [""] + unknowns + [""] + limits)

    # The UI contract (lib/local-report.ts) rejects reports longer than 100_000 chars.
    # Truncate at a line boundary and say so — never silently.
    if len(text) > _MAX_REPORT_CHARS:
        head = text[:_MAX_REPORT_CHARS - len(_TRUNCATION_NOTE) - 2]
        head = head[: head.rfind("\n") + 1] if "\n" in head else head
        text = head + _TRUNCATION_NOTE
    return text
