import assert from "node:assert/strict"
import test from "node:test"
import { fixturesEnabled } from "../ui-fixtures.ts"

test("fixtures require the explicit query flag and stay disabled in production", () => {
  const original = process.env.NODE_ENV
  try {
    process.env.NODE_ENV = "development"
    assert.equal(fixturesEnabled(""), false)
    assert.equal(fixturesEnabled("?fixtures=true"), false)
    assert.equal(fixturesEnabled("?fixtures=1"), true)
    process.env.NODE_ENV = "production"
    assert.equal(fixturesEnabled("?fixtures=1"), false)
  } finally {
    if (original === undefined) delete process.env.NODE_ENV
    else process.env.NODE_ENV = original
  }
})
