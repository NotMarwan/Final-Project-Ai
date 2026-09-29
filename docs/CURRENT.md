# Current project state

This is the sole current-state entry point. Generated from this checkout and recorded evidence. No document named “final”, old version label, presentation, or archived agent prompt overrides it.

Implementation fingerprint: `c3616e683ce2762b6fd581eec390d2d485517d478d4350e6200871264e881215`. Package-declared versions: Next `16.3.6`, React `19.2.4`, Tailwind `^4.1.9`. These are declarations; package-lock.json defines the resolved installation.

## Implemented surface

Next dashboard: app/ and components/. Backend: backend/api.py and its pipeline modules. Root frontend source is authoritative; frontend/, design_extract/ and presentations are not alternate runtime authorities. The registered run identifies its actually loaded model and providers. The current pipeline has camera-scoped decisions, source timestamps, bounded model workers, model-specific observation identities, and health telemetry. The dashboard distinguishes replay/offline/stale observations and offers a local Arabic factual summary. These implemented capabilities do not certify accuracy or camera acceptance.

## Latest registered evidence, not a readiness claim

Registered report: `bench/results/integration-review-2026-09-29/report.json`. Workload: 75-second 480x360 file replay, 25-second warmup, 50-second measured interval, all detection active, one MJPEG and two SSE clients, and three unchanged controls. Recorded render FPS median: 30.0. This is not live camera throughput unless the report explicitly establishes it.

No live-camera run or 60-minute soak was performed. No PresentOnly camera device was available during the integration environment check.

Final reviewed source e1a5636: CUDA replay on Windows/Python 3.12, RTX 3060, Torch 2.3.0+cu118 and ONNX Runtime GPU 1.18.0. All 62 backend source hashes match. Post-warmup person/weapon/violence calls: 240/19/147; render FPS p05/p50/p95: 25/30/30.55; model medians: 23.61385/48.8769/97.4766 ms. Three unchanged control routes each returned 100 successful requests; p95 was 15.51099 ms for threshold, 5.09966 ms for cooldown and 4.235125 ms for decision configuration. The development-only unverified-calibration override was explicit. Python contracts: 860 passed, 10 skipped, 5 integration tests deselected; 108 Node tests and all 8 browser checks passed across the full and corrected focused runs. Typecheck, lint and production build passed; npm audit found zero known vulnerabilities. No alert occurred in this unlabeled throughput replay; accuracy, calibration, event latency, live G-15 and 60-minute gates remain unverified. Prior auxiliary G-02/G-03 evaluation failures remain unresolved.

Read docs/ISSUES.md for unresolved defects and the gate report registered in docs/evidence.json. Changing this registry requires new evidence and review; it never triggers gate acceptance.

Recorded backend source hashes still match; hardware, environment and camera availability are not continuously monitored.

## Work authority

The current user task controls scope. docs/PLAN.md holds pending rebuild work, not completed features. Documentation/design consolidation is authorized independently of blocked live measurements. Do not reopen settled historical debates or import old freezes, agent approval loops or obsolete model claims. Verify a disputed current fact against code and evidence and correct the one canonical document.

## Refresh

Run `npm run docs:sync` after source changes, then `npm run docs:check`. Generated fields follow implementation; measured claims require new evidence and must never be upgraded just by refreshing documentation. See docs/MAINTENANCE.md.

## Living blueprint (generated pointer)

The scoped, non-authoritative living blueprint extends this status document: `docs/blueprint/INDEX.md` (generated) from `docs/blueprint/index.json` (validated input). ID namespaces: `F-01`…`F-49` runtime features, `U-01`…`U-10` UI screens, `SC-1`…`SC-10` shared contracts, `S-01`…`S-22` ownership slices, `B-1`…`B-10` baseline integrity findings, `N-1`…`N-16` negative findings, `R-1`…`R-8` risks. Registered entries: contract 10, finding 35, runtime 62, slice 22, ui 10. `npm run docs:check` fails when the index disagrees with recorded source fingerprints or when a canonical document cites an unknown blueprint id; stale entries must be re-assessed in `docs/blueprint/index.json`, never silenced. The blueprint is not a status or design authority.
