---
authority: scoped
non_authoritative: true
---
# Reviewer guide — candidate `codex/sentinel-30-integration` (WT-30)

Working tree: `C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-30`.
`candidate_sha` at handoff: see the latest commit on the branch (`git log -1`). The primary checkout is
read-only and was never written to by this workstream.

## Commit order to review

1. `merge: WT-03 docs-gen` (blueprint seed, ID registry, docs contract/generator).
2. `merge: WT-28 security-api` → 3. `-13` → 4. `-15` → 5. `-16` → 6. `-14` → 7. `-18` → 8. `-19` →
9. `-20` (G-06 gate) → 10. `-21` (face bootstrap, camera_worker union) → 11. `-22` (capture-loop rule) →
12. `-23` (+ integrator enhancement seam) → 13. `-24` → 14. `-25` → 15. `-26` → 16. `-27` → 17. `-17` →
18. `-12` (eval harness + fixtures; missed by the original brief, merged in the repair round).
19-26. the eight research-doc merges (`-04`…`-11`).
Then the docs commits (fingerprint re-assessment, regenerations, blueprint ID table, handoff bundle,
this repair round). Every merge commit message carries its own commits-taken/conflicts/resolutions record.

## Reproduce

```bash
cd "C:/Users/PCD/Downloads/jobs/sentinel-campaign/wt-30"
npm run docs:sync && npm run docs:check          # GREEN on the candidate
py -3 -m py_compile backend/api.py backend/metrics.py backend/pipeline_render.py
py -3.14 -m pytest backend/tests -q              # scoped backend suites
py -3.14 -m pytest tests -q                      # top-level suites (incl. bench/eval)
npm run typecheck ; npm run lint ; npm run build # NOTE: require node_modules in this worktree
```

**G-06 startup reality (reproduce exactly):** a bare backend start REFUSES to serve — the startup
calibration gate raises `CalibrationArtifactError` (G-06, deliberate: no calibration artifact, no
silent "unverified" scores). Endpoints serve only with the loud dev override:

```bash
AI_SENTINEL_CALIBRATION_UNVERIFIED_OVERRIDE=I-UNDERSTAND-SCORES-ARE-UNVERIFIED python -m backend.api
```

**Environment caveat (measured):** the worktree has no `node_modules`, so `npm run typecheck` /
`npm run lint` could not execute as written (`tsc` not found; ESLint cannot resolve
`typescript-eslint`). Running the primary checkout's binaries against this worktree produces
module-resolution noise (`Cannot find module 'react'`, `clsx`, `@types/node`) which is **not** a type
verdict. The `hooks/use-modal-focus.ts` TS18046 ("'node'/'last'/'first' is of type 'unknown'") errors
are part of that noise — with React types present they disappear (WT-29 verified). One error in that
noise was **real**: `lib/detection-types.ts(343,5)` (`personCount` was `number | null` against a
`number` field) — **now fixed** on the candidate (`rawPersonCount ?? activeTrackCount` alias fallback,
matching the interface's documented "legacy alias of activeTrackCount" semantics).

## Required external assets (never committed)

- ONNX: `person_yolo.onnx` sha256 `3fafb13e…e60b8`, `weapon_yolo.onnx` sha256 `96991cd5…75aef`
  (`scripts/provision_assets.py --source <dir|URL>` fetches/copies + verifies).
- KTH fixtures: per `docs/campaign/eval/12-fixture-manifest.json` (36 clips; walking/handwaving/boxing).
- WT-23 tier-1 (harness only, untracked): `assets/RealESRGAN_x4plus.pth` `4fa0d389…d682f1`,
  YuNet `assets/face_detection_yunet_2023mar.onnx` `8f2383e4…52fa4`, SFace `0ba9fbfa…4e79`,
  LPIPS 0.1.4 wheel; see `docs/campaign/engineering/23-enhancement-honesty.md` §7.

## Rollback

- Device/runtime: `scripts/select_onnx_runtime.py` selects the provider policy; CPU rollback = force the
  CPU EP (documented in `docs/campaign/accel/16-inference-acceleration.md`).
- Any single merge: `git revert -m 1 <merge-sha>` on the candidate branch (each merge is one commit).
- Generated docs: re-run `npm run docs:sync`; never hand-edit.

## Known risks

1. **Partially validated unions.** `backend/api.py`'s WT-17 unions and the assembled frontend
   (`lib/sentinel-store.tsx`, `app/page.tsx`, overview/incident components) were resolved by reading
   code plus targeted suite runs (threat dispatch 2/2, intrusion contract 18/18 after the repair round).
   Still unrun on the candidate: `tests/test_transport_identity.py`,
   `tests/test_decision_overlay_burnin.py`, `tests/frame-correlation.test.mjs`, `npm run build`.
2. **Blueprint semantic re-assessment** is only mechanical (fingerprints re-pinned; entry claims and
   branch-delta fold-in still owed) — recorded in the index's `known_limitations`.
3. 16 GB RAM pressure and multi-camera VRAM ceilings (WT-15 EXP-15.05).
4. KTH aux-domain limits: action-level labels, no identity GT — HOTA/IDF1 need identity ground truth.
5. No camera device in this environment: every measurement is file media; live gates stay open.
6. Tool-layer command duplication (this session's harness re-sent some calls) — repaired in place, but
   a reviewer should diff the docs commits and the merge resolutions rather than trusting summaries.

## Preservation check (WT-29 C-5 forensics adopted; measured)

| Check | Result |
|---|---|
| Tracked content, weights, settings | **preserved byte-identical** (primary branch/HEAD `final-demo-transfer` @ `e86d34b5…`; all four model hashes match the preflight record) |
| Untracked space | exactly **one small campaign artifact** + **one metadata event** |
| Campaign artifact | `smoke-home.html` created **2026-09-28T23:19:11Z** in the primary checkout by campaign browser tooling — **disclosed, NOT deleted** |
| Metadata event | `desktop/package-lock.json` **ctime 19:58Z rename-into-place**, content unchanged since May — campaign-window metadata event, content preserved |
| Verdict | tracked content + weights + settings preserved byte-identical; untracked space saw exactly one small campaign artifact + one metadata event; the pre-existing dirty work stands |

## Decisions that need independent review

CUDA promotion (EXP-01/02/03), SC-5 key management, severity tolerance, the triage API shape,
G-04 disposition (stride-4 floor), G-02/G-03 FAILED dispositions (47.06 false alerts/camera-hour on
KTH-aux; recall 0.140/0.138/2-of-12 at threshold 0.45), VLM deferred (EXP-2701 blocked), and the
integrator-authored WT-23 enhancement seam (trigger choice = whole-frame crop).
