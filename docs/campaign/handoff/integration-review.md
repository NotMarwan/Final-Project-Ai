---
authority: scoped
non_authoritative: true
---

# Campaign integration review

This scoped record audits the 30 parallel campaign workstreams. It is not product status, a design authority, or acceptance evidence. `docs/PLAN.md`, `docs/ISSUES.md`, generated `docs/CURRENT.md`, source code, and registered reports remain the applicable authorities. Research proposals are not implemented behavior; measured replay and unit-test contracts are not deployment accuracy or live readiness. Retired prompts and gates were not reintroduced.

## Ancestry and branch coverage

The campaign branches started at baseline `e86d34b5d16abcc133ad3470c8d135d00b2423d4`. In the assembled candidate, the tips for WT-01…WT-28 and WT-30 were ancestors of `224a90979621f1a3ec123e7d4e75af556816fdfc`. WT-29's four commits were subsequently fast-forwarded; review HEAD is `3e91b39d2f48f2ecc8175d7c711a7bc05d2f6c63`. No source-branch commit omission was found. WT-18's handoff cited `e66129c`, but later tip `c78a5763` is also integrated; it contains the updated negative weapon-free fixture cases. The stale handoff reference should not be mistaken for the integrated branch tip.

This only establishes commit ancestry. Untracked artifacts found by metadata in the campaign worktrees were not pulled in as evidence or dependencies: WT-05 has third-party clone directories and helper scripts; WT-08 has YuNet benchmark/model assets; WT-12 has a post-handoff pass-1 report and 36 outputs; WT-21 has face/YuNet asset folders; WT-23 has enhancement model weights/scripts/measurements; WT-27 has VLM assets and fixture results. These are unreviewed local files, not candidate deliverables. Other campaign worktrees had no normal untracked or modified files at audit time. Original primary modifications were copied to an ignored local backup with SHA-256 verification before main checkout. Model weights are preserved in place; optional unreviewed source copies are kept out of the active runtime.

## Thirty-workstream disposition

| Agent | Disposition and useful integrated output | Remaining action or limit |
|---|---|---|
| WT-01 | Integrated runtime map, ownership map and verification record. | Blueprint semantics and source fingerprints are reassessed; no runtime gate follows from the map. |
| WT-02 | Integrated design map and UI/API contracts. | Final role/API contracts and offline browser flows pass; live authenticated deployment remains separate. |
| WT-03 | Integrated docs contract and initial living blueprint seed. | Current/manifest outputs and blueprint fingerprints are synchronized; strict docs checks pass. |
| WT-04 | Integrated commercial competitor research. | Vendor Dahua documentation was login-gated; no vendor capability or accuracy was independently verified. |
| WT-05 | Integrated open-source competitor research. | Untracked clones remain outside candidate; review licensing and deployment fit before adopting any code. |
| WT-06 | Integrated violence research. | No labeled hugging/handshake/phone benign suite; KTH is auxiliary and the measured evaluation fails G-02/G-03. |
| WT-07 | Integrated weapon research. | Dataset names/labels are unresolved and no weapon-positive ground truth exists; recall is unmeasured. |
| WT-08 | Integrated faces, tracking and imaging research. | Super-resolution can invent forensic detail; YuNet/model assets in the worktree are untracked and do not establish product behavior. |
| WT-09 | Integrated inference/runtime research. | `torch.compile` was excluded; no compilation or resource benefit is measured. |
| WT-10 | Integrated camera/transport research. | No camera device was available; negotiation and live transport behavior remain unmeasured. |
| WT-11 | Integrated web-app and analytics research. | Competitor account-gated metrics were not verified; do not cite vendor accuracy as comparative evidence. |
| WT-12 | Integrated evaluation harness, protocols and auxiliary fixtures. | Required domains, event-onset labels and disjoint calibration inputs are absent. A post-handoff pass-1 output exists only as untracked worktree metadata and was not registered. |
| WT-13 | Integrated measurement and telemetry slice; basic detection and frame/result queue telemetry is wired into the API. | Focused tests cover the counters, but evidence-queue, ledger, disk-headroom and camera-time telemetry plus live under-load behavior remain unverified. |
| WT-14 | Integrated capture-quality changes. | Camera negotiation, real-device image quality and contended latency await a physical camera run. |
| WT-15 | Integrated worker/resource architecture changes. | Overload, reconnect and multi-source resource regimes remain unmeasured. |
| WT-16 | Integrated CUDA provider/session and benchmark work. Four valid matched CPU/CUDA replay reports exist on source revision `1218a6cb`. | The final replay reports 30 FPS median, p05 25, active model calls and 62/62 source hashes matching. Historical matched CPU/CUDA pairs remain at their original revision; fresh-install requirements still select CPU. |
| WT-17 | Integrated video transport/synchronization work. | E-5 transport rows and live synchronization under load remain unmeasured. |
| WT-18 | Integrated weapon decoder/NMS/taxonomy work through tip `c78a5763`; later weapon-free negative fixtures are present. | No weapon-positive ground truth; small-weapon recall and domain performance remain unknown. |
| WT-19 | Integrated violence decision/window changes. | WT-29's auxiliary evaluation has false alerts and low recall; G-02/G-03 remain failed on that set. |
| WT-20 | Integrated decision/calibration interfaces and startup guard. | No validated calibration artifact or ECE; missing-artifact fail-closed behavior is not calibration acceptance. |
| WT-21 | Integrated person detection and incident face detection/capture; retired identity recognition routes remain absent. | No representative face ground truth; local face/YuNet assets are untracked and do not prove detection quality or identity matching. |
| WT-22 | Integrated tracking/counting/best-frame slice. | HOTA/IDF1 and count quality lack labeled fixtures; evaluate before reporting tracking performance. |
| WT-23 | Integrated enhancement code slice. | Worktree weights and measurement files are untracked; timing is an upper bound pending clean rerun and asset/provenance review. |
| WT-24 | Integrated evidence pipeline work and contracts. | Codec, hashes, partial capture, epoch and access contracts pass; camera evidence duration/playback acceptance remains open. |
| WT-25 | Integrated operator UI/alert changes. | Viewer/admin contracts pass; triage remains session-scoped and persistence is a remaining product decision. |
| WT-26 | Integrated evidence-ledger statistics route, frontend fetch and labeled session fallback with window/camera semantics. | Evidence records do not represent every alert and persisted history has no drill-through; active-camera availability remains unavailable. |
| WT-27 | Integrated Arabic reporting and offline code/research. | VLM verdict is blocked by incomplete/unverified download; offline full-demo proof and Arabic quality are open. |
| WT-28 | Integrated explicit optional-import health, `/security/session`, and admin authorization for `/api/analyze`; focused behavior contracts exist. | Final route contracts pass; owner-led credential rotation remains necessary. Protected reads require viewer authorization and mutations require admin. |
| WT-29 | Four evaluation commits fast-forwarded to the review HEAD; records the independent KTH and weapon-free results and C1-C8 dispositions. | G-02/G-03 fail on the auxiliary evaluation; G-04/G-06 and live G-15/soak remain unmeasured. The pass/fail report does not certify the product. |
| WT-30 | Integrated assembled candidate, experiment records and reproducibility notes. | Final source contract checks, production build and a fresh valid CUDA replay are complete; live/model-quality gates remain open. |

## Reproducible runtime evidence and its boundary

The earlier registered campaign runtime report was `bench/results/campaign-accel-2026-09-29/fullpipeline-cuda-2/report.json`; it has `workload_valid: true`, with 244 person, 20 weapon and 146 violence calls. The paired CPU and CUDA reports use the same measured source revision and all four passed workload validity. CUDA-2 reports render p05/p50/p95 of 26.45/30/31 FPS and person/weapon/violence medians of 22.0456/52.8575/85.4845 ms. The CPU pair reports person medians 78.56895/82.5814 ms and weapon medians 515.8952/539.6538 ms. These are 50-second, three-control file-replay measurements after warmup. The environment was Windows 11, Python 3.12, RTX 3060, Torch 2.3.0+cu118 and ONNX Runtime GPU 1.18.0. They demonstrate active CUDA inference and a matched replay speed improvement, not accuracy, end-to-end event latency, live-camera throughput, default GPU installation, or acceptance on current code. The report's 36 source hashes match 16 backend files in the current review tree.

The target venv reports ONNX Runtime 1.18.0 with TensorRT/CUDA/CPU provider names and Torch CUDA available; a returned TensorRT provider name is not evidence that TensorRT can initialize. No PresentOnly camera device was available, and no live run or 60-minute soak was completed. The `backend/requirements.txt` CPU pin remains the fresh-install default. Keep the earlier CPU/CUDA pairs for their original comparison; the final exact-source CUDA replay below is the current engineering measurement.

WT-29 measured its auxiliary KTH violence set at threshold 0.45: frame recall 0.140, window recall 0.138, event recall 2/12, alert precision 2/9; 7 false alerts in 0.1487 negative camera-hours (47.06 per hour). Four false alerts were on negative clips (three handwaving, one walking); three were unmatched boxing-positive sessions. Its weapon set produced 4 false positives in 36 weapon-free clips and had no weapon-positive truth. These results fail the tested G-02/G-03 slice, cannot support domain accuracy claims, and must not be used to tune on test truth. G-04 lacks independent event-onset labels. G-06 has no calibration artifact/ECE. Keep these failures and unknowns visible.

## Final integration verification

The reviewed source is committed locally as `e1a5636`. The fresh registered replay is `bench/results/integration-review-2026-09-29/report.json`: workload valid, runtime exit zero, all 62 backend hashes match. Post-warmup render p05/p50/p95 is 25/30/30.55 FPS; person/weapon/violence completed 240/19/147 calls with median model times 23.61385/48.8769/97.4766 ms. Each of the three unchanged controls completed 100 successful calls, with p95 at or below 15.51099 ms. One MJPEG and two SSE clients were active. No independent labels or onset times were used; there were zero alerts, which cannot be interpreted as a model-quality result.

817 backend/root Python tests and 43 harness tests pass (860 total); 108 Node tests pass. Ten optional/packaging tests skip and five integration tests were deselected. All eight browser checks pass across the full run and focused correction. Typecheck, lint, production build and strict docs checks pass. The dependency audit reports zero known vulnerabilities. `integration-validation.json` records exact scope and limitations.

The root integrated lifecycle recovery, fresh-observation score provenance, checkpoint-bound calibration profiles, epoch-safe partial evidence, admin mutations, authenticated evidence, immutable report publication, explicit local-report provenance, half-open statistics windows and atomic asset provisioning. An independent Astra review found two P2 issues (epoch finalization race and mismatched class selection); both were fixed, regression-tested and independently rechecked. Browser fixes preserve Next.js dev-origin protection and make offline test errors origin-specific.

The kit is pinned to upstream `30b7d0bb7e9b3b9a7d27e78a11c468f95c4cf704`, Pro profile, Apache-2.0. Project configuration keeps Astra orchestration/review and Luna workers; actual bounded Luna workers and an Astra reviewer were used. Host approvals remain inherited and GPU workloads serialized.

Main delivery uses the exact reviewed file tree with the previous local and remote main commits as parents. Campaign history remains local because old commits contain credential matches; those commits are not made newly reachable on the remote. No force push or history rewrite is used. Thirty-workstream coverage is established in the review checkout, while the clean main commit delivers its reviewed result. Original user modifications and all four model assets are preserved by hashes.

Remaining work is targeted-domain positive/negative evaluation, weapon-positive labels, disjoint calibration and held-out ECE, independent onset timing, live capture, transport stress, enhancement/VLM evaluation and a 60-minute soak. None was passed by prose or by the replay.

## Missing data and setup inputs

The immediate blockers are a working camera, independently labeled benign domains (hugging, handshakes, waving, walking, phone use), representative violence/close-range positives, weapon-positive examples, independent event-onset timestamps and a disjoint calibration set. KTH auxiliary clips cannot replace these. The final replay used the recorded Windows/Python 3.12 environment, selected ONNX Runtime wheel, Torch CUDA 11.8, verified assets and exact source hashes; a future CPU/GPU comparison requires matched configurations. Existing person/weapon ONNX assets were hash-verified when staged, but the two ONNX files do not cover every startup asset. Calibration is currently required to start unless the explicit development-only override is supplied. The post-upgrade browser checks and production build used the updated lockfile.
