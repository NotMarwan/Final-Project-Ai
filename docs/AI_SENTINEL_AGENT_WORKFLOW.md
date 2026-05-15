# AI-Sentinel Agent Workflow Guide

**Note:** The agent definitions are now fully contained in `.kilo/kilo.jsonc`. The Markdown files in `.kilo/agent/` serve as backup documentation only.

## Recommended Step-by-Step Workflow

Follow this sequence the first time you use the AI-Sentinel agent system.

### Step 1: Activate the Orchestrator

In Kilo Code's agent selector (status bar), choose **ai-sentinel-orchestrator**. Alternatively, use the command palette: "Kilo: Set Agent" → "ai-sentinel-orchestrator".

### Step 2: Send the Kickoff Message

Copy and paste this exact message into the chat:

```
Use the AI-Sentinel agent system. Act as ai-sentinel-orchestrator. First inspect the repository, then delegate to the graduation judge, company adoption reviewer, bug hunter, ML decision layer reviewer, backend reviewer, frontend reviewer, security/privacy reviewer, QA verifier, demo readiness agent, and product vision agent. Merge their findings into one final P0/P1/P2/P3 roadmap. Do not modify source code yet. Documentation and Kilo agent configuration edits are allowed. Protect best_model.pt, secrets, and the confirmed_alert safety rule.
```

Press Enter. The orchestrator will begin repository discovery and then delegate tasks to each subagent.

### Step 3: Wait for Delegation Output

The orchestrator will call each subagent sequentially, collecting their reports. This may take a few minutes as the agent reads files and thinks. You'll see messages like:

```
[Orchestrator] Delegating to ai-sentinel-graduation-judge...
[ai-sentinel-graduation-judge] Evaluating project...
...
[Orchestrator] All reports received. Consolidating...
```

### Step 4: Receive the Final Integrated Report

The orchestrator will output a comprehensive report containing:

- **Executive Summary** — project health in one paragraph
- **Scores Card** — graduation, adoption, demo, code quality, security
- **Critical Blockers (P0)** — must fix before demo
- **High Priority (P1)** — before graduation defense
- **Medium (P2)** — before company pilot
- **Long-term (P3)** — visionary features
- **This-Week Action Plan** — day-by-day checklist
- **Files Changed** — docs/config updates already made
- **Files Recommended** — source code changes to consider
- **Residual Risks** — what remains even after fixes
- **Demo Verdict** — Go/No-Go with reasoning

### Step 5: Review & Approve

Read the final report carefully. Check the P0 items — are they acceptable? The orchestrator may have already made safe documentation edits. For any source code changes, it will ask for explicit approval with a patch.

Approve changes you agree with. You can ask the orchestrator to implement safe changes now, or defer risky ones.

### Step 6: Re-run Verification (Optional)

After implementing fixes, you can re-run the orchestrator with a follow-up message:

```
Re-audit the project with all review agents again. Verify that P0 issues are resolved and update the roadmap.
```

This produces a second-pass report showing improvement.

## Manual Inspection

If you want to consult a specific domain without the full orchestration, use the agent name directly:

- `@ai-sentinel-ml-decision-layer-reviewer` — "Verify V2 safety rule and SHA mismatch"
- `@ai-sentinel-demo-readiness-agent` — "Give me the pre-demo checklist"
- `@ai-sentinel-testing-qa-verification` — "Propose a minimal test plan"

## Typical Times

- Full orchestration run: 5–10 minutes (agents read files and synthesize)
- Individual subagent query: 1–3 minutes

## After the Review

Once you have a final roadmap:
1. Tackle P0 items immediately (same day)
2. Schedule P1 items before defense date
3. Archive P2/P3 for future development
4. Use the generated documentation (talking points, demo script) for presentation

## Need to Restart?

If you want to clear the context and start fresh, open a new Kilo chat session. The agents are permanently installed; just activate the orchestrator again.

---

**Guide version:** 1.0 — AI-Sentinel Review System
