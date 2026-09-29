---
authority: scoped
non_authoritative: true
---
# Campaign scoped-artifact space

This directory is the campaign's **scoped, non-authoritative** artifact space: research catalogs,
experiment records, workstream reports and verification logs land here. It is explicitly NOT a
status or design authority.

- `docs/CURRENT.md` remains the sole current-status entry point (generated).
- `docs/DESIGN.md` remains the sole design-system authority (generated).
- `docs/PLAN.md` holds pending work; `docs/ISSUES.md` holds defects.
- The living blueprint (`docs/blueprint/index.json` + generated `docs/blueprint/INDEX.md`) extends
  those documents with stable IDs; it is scoped and non-authoritative too.

## Rules enforced by `npm run docs:check`

1. Every `docs/campaign/**/*.md` (and `docs/blueprint/**/*.md`) MUST start with the machine-readable
   non-authority marker:

   ```
   ---
   authority: scoped
   non_authoritative: true
   ---
   ```

   Alternatively a file may be listed in `docs/campaign/index.json` (or `docs/blueprint/index.json`).
2. Scoped documents MUST NOT be added to `canonical_docs` in `docs/authority.json` — the checker
   rejects any scoped path promoted to canonical ("Scoped artifact promoted to canonical document").
3. Scoped documents must not carry competing status claims or design-system definitions. Cite
   `docs/CURRENT.md`/`docs/DESIGN.md` and the blueprint IDs (`F-##`, `U-##`, `SC-#`, `S-##`,
   findings `B-#`/`N-#`/`R-#`) instead of inventing parallel numbering.

## Layout

- `docs/campaign/research/NN-<slug>.md` — per-workstream research catalogs (NN = campaign workstream number).
- `docs/campaign/security/` — security-audit scoped reports.
- `docs/campaign/<topic>/` — other scoped catalogs and experiment records.
- `docs/campaign/index.json` — optional alternate registry for scoped documents (path listing).
