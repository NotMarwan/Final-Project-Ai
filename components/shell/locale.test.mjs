import assert from "node:assert/strict"
import { test } from "node:test"
import { formatDateTime24, formatTime24, normalizeLatinDigits } from "./locale.ts"

test("normalizes Arabic and Persian numerals for readings", () => {
  assert.equal(normalizeLatinDigits("قبل ٣٠ دقيقة · ۷۵%"), "قبل 30 دقيقة · 75%")
})

test("formats Arabic UI times in 24-hour Latin numerals", () => {
  const instant = new Date(2026, 8, 26, 17, 5)
  assert.equal(formatTime24(instant), "17:05")
  assert.match(formatDateTime24(instant), /17:05/)
  assert.doesNotMatch(formatDateTime24(instant), /[\u0660-\u0669\u06f0-\u06f9]/u)
})
