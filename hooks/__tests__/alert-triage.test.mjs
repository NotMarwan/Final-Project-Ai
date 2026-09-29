import assert from "node:assert/strict"
import { test } from "node:test"
import {
  SEVERITY_LABEL,
  TRIAGE_ALLOWED,
  TRIAGE_MAX_TRACKED,
  compareBySeverity,
  mergeTriageRecord,
  normalizeSeverity,
  parseAlertEnvelope,
  parseStreamFrame,
  parseTriageEnvelope,
  parseTriageRecord,
  reduceTriage,
  triageActionRecord,
} from "../../lib/sentinel-selectors.ts"

const ALERT = {
  id: "alert-1",
  cameraId: "CAM-01",
  severity: "high",
  type: "Violence",
  confidence: 70,
  timestamp: "00:00:00 UTC",
  isoTime: "2026-09-29T00:00:00+00:00",
  location: "Test location",
}

const TRIAGE = { state: "in_progress", action: "acknowledge", actor: "viewer", at: "2026-09-29T00:00:01+00:00" }

test("severity labels are a single Arabic source", () => {
  assert.deepEqual(SEVERITY_LABEL, { critical: "حرج", high: "مرتفع", medium: "متوسط" })
})

test("severity normalization accepts the producer's none/low band without losing the alert", () => {
  assert.equal(normalizeSeverity("critical"), "critical")
  assert.equal(normalizeSeverity("high"), "high")
  assert.equal(normalizeSeverity("medium"), "medium")
  // backend/decision_config.py severity_for() can return "none"; dropping a
  // confirmed alert silently is worse than the lowest displayable tier (R-3).
  assert.equal(normalizeSeverity("none"), "medium")
  assert.equal(normalizeSeverity("low"), "medium")
  assert.equal(normalizeSeverity("severe"), null)
  assert.equal(normalizeSeverity(undefined), null)
})

test("an alert with severity none is still parsed (regression: silent drop)", () => {
  const parsed = parseAlertEnvelope({ ...ALERT, severity: "none" })
  assert.ok(parsed, "severity none must not drop a confirmed alert")
  assert.equal(parsed.severity, "medium")
  assert.equal(parseAlertEnvelope({ ...ALERT, severity: "severe" }), null)
})

test("severity ordering is critical first with newest-first ties", () => {
  const older = { severity: "critical", isoTime: "2026-09-29T00:00:00+00:00" }
  const newer = { severity: "critical", isoTime: "2026-09-29T00:05:00+00:00" }
  const medium = { severity: "medium", isoTime: "2026-09-29T00:10:00+00:00" }
  assert.deepEqual([medium, older, newer].sort(compareBySeverity), [newer, older, medium])
})

test("triage transitions match the documented workflow", () => {
  assert.equal(reduceTriage("new", "acknowledge"), "in_progress")
  assert.equal(reduceTriage("in_progress", "hold"), "on_hold")
  assert.equal(reduceTriage("on_hold", "resume"), "in_progress")
  assert.equal(reduceTriage("on_hold", "resolve"), "resolved")
  assert.equal(reduceTriage("resolved", "reopen"), "in_progress")
  assert.equal(reduceTriage("new", "hold"), null)
  assert.equal(reduceTriage("resolved", "resolve"), null)
  assert.deepEqual(TRIAGE_ALLOWED.new, ["acknowledge", "resolve"])
  assert.deepEqual(TRIAGE_ALLOWED.resolved, ["reopen"])
})

test("a session transition records actor, timestamp and history", () => {
  const first = triageActionRecord(undefined, "acknowledge", "", 1_000)
  assert.equal(first.state, "in_progress")
  assert.equal(first.actor, "غير معروف")
  assert.equal(first.source, "session")
  assert.deepEqual(first.history, [{ action: "acknowledge", actor: "غير معروف", at: 1_000 }])

  const second = triageActionRecord(first, "hold", "admin", 2_000)
  assert.equal(second.state, "on_hold")
  assert.deepEqual(second.history.map((entry) => entry.action), ["acknowledge", "hold"])
  assert.equal(triageActionRecord(second, "acknowledge", "admin", 3_000), null)
})

test("triage records keep the newest state and stay bounded", () => {
  const server = { ...TRIAGE, source: "server", history: [] }
  const merged = mergeTriageRecord({}, "alert-1", server)
  assert.equal(merged["alert-1"].state, "in_progress")

  // A stale server echo must not overwrite a newer session record.
  const newer = { ...server, state: "resolved", at: "2026-09-29T00:00:05+00:00" }
  assert.equal(mergeTriageRecord(merged, "alert-1", newer)["alert-1"].state, "resolved")
  assert.equal(mergeTriageRecord(mergeTriageRecord(merged, "alert-1", newer), "alert-1", server)["alert-1"].state, "resolved")

  const oversized = Object.fromEntries(Array.from({ length: TRIAGE_MAX_TRACKED }, (_, index) => [`alert-${index}`, server]))
  assert.equal(Object.keys(mergeTriageRecord(oversized, "alert-last", server)).length, TRIAGE_MAX_TRACKED)
})

test("triage records parse from the API and reject unknown vocabulary", () => {
  const record = parseTriageRecord(TRIAGE)
  assert.equal(record.state, "in_progress")
  assert.equal(record.source, "server")
  assert.equal(record.actor, "viewer")
  assert.equal(record.at, Date.parse(TRIAGE.at))
  assert.deepEqual(record.history, [])

  const withHistory = parseTriageRecord({ ...TRIAGE, history: [{ action: "hold", actor: "admin", at: TRIAGE.at }, "junk", { action: "boom", at: TRIAGE.at }] })
  assert.deepEqual(withHistory.history.map((entry) => entry.action), ["hold"])

  assert.equal(parseTriageRecord({ ...TRIAGE, state: "melted" }), null)
  assert.equal(parseTriageRecord({ ...TRIAGE, action: "delete" }), null)
  assert.equal(parseTriageRecord({ ...TRIAGE, at: "not-a-time" }), null)
  assert.equal(parseTriageRecord({ ...TRIAGE, source: "session" }).source, "session")
})

test("alert_triage frames are routed to the triage branch, not parsed as alerts", () => {
  const frame = parseTriageEnvelope({ type: "alert_triage", alertId: "alert-1", triage: TRIAGE })
  assert.equal(frame.alertId, "alert-1")
  assert.equal(frame.record.state, "in_progress")
  assert.equal(parseTriageEnvelope({ type: "alert_triage", alertId: "../escape", triage: TRIAGE }), null)
  assert.equal(parseTriageEnvelope({ type: "alert_triage", alertId: "alert-1", triage: { state: "new" } }), null)
})

test("stream frames classify alerts, triage, person counts and malformed payloads", () => {
  assert.equal(parseStreamFrame(JSON.stringify(ALERT)).kind, "alert")
  assert.equal(parseStreamFrame(JSON.stringify({ type: "alert_triage", alertId: "alert-1", triage: TRIAGE })).kind, "triage")
  assert.deepEqual(parseStreamFrame(JSON.stringify({ type: "person_detection", personCount: 3 })), { kind: "person", count: 3 })
  assert.equal(parseStreamFrame(JSON.stringify({ type: "VLM_Report", id: "alert-1" })).kind, "ignored")
  assert.equal(parseStreamFrame(JSON.stringify({ id: "alert-1", severity: "severe" })).kind, "rejected")
  assert.equal(parseStreamFrame("{not json").kind, "rejected")
})
