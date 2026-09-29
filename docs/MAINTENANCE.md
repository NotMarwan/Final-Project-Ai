# Keeping one current version

1. Read AGENTS.md and CURRENT.md. Change the implementation or the existing canonical document, not a new competing status/plan.
2. For UI changes edit app/globals.css and the actual components. The duplicate stylesheet is an import-only alias.
3. Run `npm run docs:sync`, review changes, then `npm run docs:check` (or npm run docs:sync / docs:check).
4. New runtime evidence must include source/environment hashes, workload, date and limitations. A source refresh cannot turn old evidence into a current pass. CURRENT.md automatically flags changes to the backend sources recorded by the baseline; environment/hardware changes still require revalidation.
5. New authoritative documents must be registered in authority.json and linked here or in README.md. Retired files must stay absent. Do not bypass checks by deleting retirement records. Add a reviewed ADR only for a new decision; do not reopen resolved historical alternatives.

Derived files: CURRENT.md, DESIGN.md, design-tokens.json, design-preview.html, SOURCE-MANIFEST.json. They are checked against source and must not be hand-edited. Narrative sources: PLAN.md, ISSUES.md, RUNBOOK.md and this file. Register future measured status in docs/evidence.json with the report path, workload, date and limitations as part of the same reviewed change.

The full local source/design check is wired into prebuild. CI runs --check-design plus the guard tests: it checks documentation authority and the portable design reference. The local source snapshot includes pre-existing uncommitted source files and raw Windows baseline evidence, so CI deliberately does not certify that workstation snapshot. It detects source/design drift, extra unregistered docs, retired files reappearing and missing agent pointers. It cannot prove factual correctness of arbitrary prose or prevent an agent from ignoring instructions. Review evidence and maintain these boundaries.

Retirement recovery is a verified ZIP outside this project's working tree, excluded from default searches in the adjacent SAIF workspace. It is for explicit recovery requests only. Old contents are not mirrored under docs/archive. The ledger in authority.json retains only file names, not old instructions.
