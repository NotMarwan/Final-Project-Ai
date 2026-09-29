# AI Sentinel — agent entry point

Read `docs/CURRENT.md`, then `docs/PLAN.md` for pending scope and `docs/DESIGN.md` for UI work. These are the only current project authorities. `docs/authority.json` registers them; `docs/ISSUES.md` holds unresolved findings. Read source files as needed, not every historical artifact.

The current user's instructions control the task. Do authorized work autonomously; do not import approval loops, obsolete freezes, thresholds, model claims or agent delegation rules from retired documents. Documentation maintenance is independent of camera availability. Rebuild dependencies and acceptance gates apply to the rebuild work specified in PLAN.md, not to unrelated authorized maintenance.

Implementation is established by source; behavior and readiness require measured evidence. Generated CURRENT/DESIGN documents identify their source fingerprint. Never turn a proposed feature into a verified feature by editing prose. Fix a contradiction in its single canonical source and regenerate derivatives. Never recreate a second project status or design-system document.

Design source: `app/globals.css`, loaded by `app/layout.tsx`, with reusable primitives in `components/ui/`. `styles/globals.css` is an import-only compatibility alias. Update source tokens, not generated design-tokens.json. Do not use presentation exports or the duplicate frontend tree as design authority.

Before finishing source/document changes run `npm run docs:sync`, review the generated diff, then `npm run docs:check`. Changing runtime source invalidates matching baseline evidence; a refresh does not pass runtime gates. Do not bypass a failed documentation check by deleting its rules.

Historical archives, backups, presentation/thesis outputs, design_extract, and off-project recovery ZIPs are not task instructions. Do not retrieve them unless the user explicitly asks for historical recovery. Do not restore retired prompts or documents automatically. The retirement ledger stores paths/hashes only.

Preserve unrelated user changes and model weights. Never log or commit secrets. Validate untrusted paths and input; enforce authentication/authorization on mutations; sanitize errors. No external messages, credential rotation, destructive source cleanup, deployment or history rewrite is authorized merely by this file. Do not assume existing security or runtime gates passed.

## Project orchestration

For substantial multi-file work, read `.agents/skills/astra-orchestrator/SKILL.md`. The project profile uses Astra for orchestration and independent review, with Luna for bounded exploration, implementation and testing. Use one writer per file and respect the host concurrency limit. The root owns integration and verification. These workflow settings do not replace the project authorities above or change host approvals.

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
