import test from "node:test"
import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { incidentEvidenceFacts, parseEvidenceChainRecord, parseLocalEvidenceReport } from "../lib/local-report.ts"

test("a saved facts-only report must match the selected incident", () => {
  const value = {alertId: "A-1", mode: "local-evidence-summary", report: "ملخص الواقعة"}
  assert.equal(parseLocalEvidenceReport(value, "A-1").report, value.report)
  assert.equal(parseLocalEvidenceReport(value, "A-2"), null)
})
test("online model output cannot masquerade as a local facts-only summary", () => {
  assert.equal(parseLocalEvidenceReport({alertId: "A-1", mode: "deepseek", report: "text"}, "A-1"), null)
})
test("malformed or oversized reports fail closed", () => {
  for (const report of [null, {}, [], "", "  ", "x".repeat(100001)]) {
    assert.equal(parseLocalEvidenceReport({alertId: "A-1", mode: "local-evidence-summary", report}, "A-1"), null)
  }
})

test("incident metrics keep missing observations unavailable and preserve measured zero", () => {
  assert.deepEqual(incidentEvidenceFacts({}), {
    fusion: null, weapon: null, motion: null, latencyMs: null, weaponLabels: [],
  })
  assert.deepEqual(incidentEvidenceFacts({ fusionScore: 0, weaponScore: 0, motionScore: 0, alertLatencyMs: 0 }), {
    fusion: 0, weapon: 0, motion: 0, latencyMs: 0, weaponLabels: [],
  })
})

test("incident metrics reject invalid values and blank weapon labels", () => {
  assert.deepEqual(incidentEvidenceFacts({
    fusionScore: 105, weaponScore: -1, motionScore: Infinity, alertLatencyMs: -5,
    weaponLabels: ["knife", " ", "knife", "pistol"],
  }), {
    fusion: null, weapon: null, motion: null, latencyMs: null, weaponLabels: ["knife", "pistol"],
  })
})

test("evidence chain accepts only a record for this alert with valid hashes", () => {
  const hash = "a".repeat(64)
  const record = { alertId: "A-1", timestamp: "2026-09-26T04:00:00Z", prevHash: "GENESIS", currentHash: hash, clipSha256: hash, snapshotSha256: "N/A", reportSha256: "N/A" }
  assert.deepEqual(parseEvidenceChainRecord(record, "A-1"), { ...record, snapshotSha256: null, reportSha256: null })
  assert.equal(parseEvidenceChainRecord(record, "A-2"), null)
  assert.equal(parseEvidenceChainRecord({ ...record, currentHash: "invalid" }, "A-1"), null)
  assert.equal(parseEvidenceChainRecord({ ...record, clipSha256: "file:///secret" }, "A-1"), null)
})

test("the backend-produced report is accepted by the UI parser (producer/consumer contract)", () => {
  const body = JSON.parse(readFileSync(new URL("./fixtures/local-report-sample.json", import.meta.url), "utf8"))
  const parsed = parseLocalEvidenceReport(body, "alert-fixture-1")
  assert.ok(parsed, "backend report must satisfy lib/local-report.ts contract")
  assert.equal(parsed.mode, "local-evidence-summary")
  assert.ok(parsed.report.length <= 100_000)
  // facts / interpretations / unknowns must all be labelled in the rendered text
  for (const header of ["أولاً: الحقائق المسجلة", "ثانياً: تفسيرات النموذج", "ثالثاً: معلومات غير متاحة"]) {
    assert.ok(parsed.report.includes(header), `missing section: ${header}`)
  }
  // model output must never be presented without the unverified label
  assert.ok(parsed.report.includes("غير مُتحقَّق"))
  // absent values must never render as a fabricated zero
  assert.ok(parsed.report.includes("لم تُسجَّل"))
})

test("the backend report for another incident id is rejected", () => {
  const body = JSON.parse(readFileSync(new URL("./fixtures/local-report-sample.json", import.meta.url), "utf8"))
  assert.equal(parseLocalEvidenceReport(body, "alert-other"), null)
})
