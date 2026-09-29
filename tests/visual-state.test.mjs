import test from "node:test"
import assert from "node:assert/strict"

import {
  areDetectionOverlayDataEqual,
  buildDemoStopPlan,
  getContainedVideoRect,
  hasWeaponVisualSignal,
  isToastSuppressedForTab,
  normalizeScoreToPercent,
  projectOverlayBox,
  sourceVisualState,
  shouldPublishDetectionSnapshot,
  resolveEvidenceUrl,
  evidenceFilename,
} from "../lib/live-visual-state.ts"

test("source state never calls a file or unverified frame live", () => {
  const base = { connected: true, stale: false, inferenceStale: false, frameReady: true, sourceKind: "live", isDemo: false, externalPlayback: false }
  assert.equal(sourceVisualState(base), "live")
  assert.equal(sourceVisualState({ ...base, sourceKind: "file" }), "replay")
  assert.equal(sourceVisualState({ ...base, sourceKind: null }), "unverified")
  assert.equal(sourceVisualState({ ...base, isDemo: true }), "replay")
  assert.equal(sourceVisualState({ ...base, externalPlayback: true }), "replay")
  assert.equal(sourceVisualState({ ...base, stale: true }), "stale")
  assert.equal(sourceVisualState({ ...base, inferenceStale: true }), "stale")
  assert.equal(sourceVisualState({ ...base, connected: false }), "stale")
  assert.equal(sourceVisualState({ ...base, sourceKind: null, connected: false }), "unverified")
  assert.equal(sourceVisualState({ ...base, sourceKind: null, connected: false, stale: true }), "unverified")
  assert.equal(sourceVisualState({ ...base, isDemo: true, connected: false }), "replay")
  assert.equal(sourceVisualState({ ...base, externalPlayback: true, connected: false }), "replay")
  assert.equal(sourceVisualState({ ...base, frameReady: false }), "loading")
  assert.equal(sourceVisualState({ ...base, frameReady: false, connected: false }), "offline")
  assert.equal(sourceVisualState({ ...base, isDemo: true, frameReady: false, connected: false, failed: true }), "offline")
})

test("detection snapshots publish at most once a second unless the decision changes", () => {
  assert.equal(shouldPublishDetectionSnapshot(1_000, 1_033, "NORMAL", "NORMAL"), false)
  assert.equal(shouldPublishDetectionSnapshot(1_000, 2_000, "NORMAL", "NORMAL"), true)
  assert.equal(shouldPublishDetectionSnapshot(1_000, 1_033, "WATCH", "CONFIRMED"), true)
  assert.equal(shouldPublishDetectionSnapshot(null, 1_033, null, "NORMAL"), true)
})

test("evidence links allow authenticated API paths and safe external HTTP URLs", () => {
  assert.equal(resolveEvidenceUrl("/evidence/clip.mp4", "http://localhost:8002"), "http://localhost:8002/evidence/clip.mp4")
  assert.equal(resolveEvidenceUrl("https://media.example/clip.mp4", "http://localhost:8002"), "https://media.example/clip.mp4")
  assert.equal(resolveEvidenceUrl("javascript:alert(1)", "http://localhost:8002"), null)
  assert.equal(resolveEvidenceUrl("https://user:secret@media.example/clip.mp4", "http://localhost:8002"), null)
  assert.equal(evidenceFilename("../INC:1"), "___INC_1.mp4")
})

function assertClose(actual, expected, epsilon = 1e-6) {
  assert.ok(Math.abs(actual - expected) <= epsilon, `expected ${actual} to be within ${epsilon} of ${expected}`)
}

function assertBoxClose(actual, expected, epsilon = 1e-6) {
  assert.equal(actual.length, expected.length)
  for (let i = 0; i < actual.length; i += 1) {
    assertClose(actual[i], expected[i], epsilon)
  }
}

const baseOverlay = {
  tracks: [
    {
      id: "P-01",
      bbox: [10, 20, 110, 220],
      confidence: 0.92,
      color: [0, 255, 255],
    },
  ],
  personCount: 1,
  isThreat: true,
  threatConfidence: 87,
  fps: 24,
  weaponScore: 0.41,
  videoWidth: 1280,
  videoHeight: 720,
  multiThreat: {
    hasViolence: true,
    hasWeapon: true,
    isMultiThreat: true,
    violenceScore: 0.87,
    weaponScore: 0.41,
    fusedScore: 0.87,
    severity: "critical",
    threatBoxes: [
      {
        id: "violence-1",
        type: "violence",
        bbox: [12, 24, 120, 240],
        confidence: 0.87,
        color: [239, 68, 68],
        label: "VIOLENCE",
      },
      {
        id: "weapon-1",
        type: "weapon",
        weaponType: "knife",
        bbox: [100, 80, 148, 156],
        confidence: 0.41,
        color: [245, 158, 11],
        label: "KNIFE",
      },
    ],
    reason: "violence+weapon",
  },
}

test("overlay equality detects video dimension changes", () => {
  const nextOverlay = {
    ...baseOverlay,
    videoWidth: 1920,
  }

  assert.equal(areDetectionOverlayDataEqual(baseOverlay, nextOverlay), false)
})

test("overlay equality detects threat box geometry changes", () => {
  const nextOverlay = {
    ...baseOverlay,
    multiThreat: {
      ...baseOverlay.multiThreat,
      threatBoxes: [
        {
          ...baseOverlay.multiThreat.threatBoxes[0],
          bbox: [12, 24, 136, 252],
        },
        baseOverlay.multiThreat.threatBoxes[1],
      ],
    },
  }

  assert.equal(areDetectionOverlayDataEqual(baseOverlay, nextOverlay), false)
})

test("toast suppression keeps live monitor visible while incidents stays quiet", () => {
  assert.equal(isToastSuppressedForTab("monitor"), false)
  assert.equal(isToastSuppressedForTab("incidents"), true)
  assert.equal(isToastSuppressedForTab("demo-clips"), false)
})

test("demo stop plan retries the same captured source id", () => {
  assert.deepEqual(buildDemoStopPlan("EXAMPLE-01"), {
    immediateStopId: "EXAMPLE-01",
    retryStopId: "EXAMPLE-01",
  })
  assert.equal(buildDemoStopPlan(null), null)
})

test("weapon visual signal treats raw model probabilities as percents", () => {
  assert.equal(normalizeScoreToPercent(0.41), 41)
  assert.equal(normalizeScoreToPercent(41), 41)
  assert.equal(hasWeaponVisualSignal(0.29), false)
  assert.equal(hasWeaponVisualSignal(0.30), true)
})

test("contained video rect preserves object-contain letterboxing offsets", () => {
  const rect = getContainedVideoRect(2000, 1000, 640, 480)
  assertClose(rect.x, 333.3333333333333)
  assertClose(rect.y, 0)
  assertClose(rect.width, 1333.3333333333333)
  assertClose(rect.height, 1000)
  assertClose(rect.scale, 2.0833333333333335)
})

test("overlay projection supports both pixel and normalized boxes", () => {
  const rect = getContainedVideoRect(2000, 1000, 640, 480)

  assertBoxClose(
    projectOverlayBox([160, 120, 320, 360], rect, 640, 480),
    [666.6666666666667, 250, 1000, 750],
  )

  assertBoxClose(
    projectOverlayBox([0.25, 0.25, 0.5, 0.75], rect, 640, 480),
    [666.6666666666667, 250, 1000, 750],
  )
})
