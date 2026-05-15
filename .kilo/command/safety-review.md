# Safety Review Command

## Purpose
Execute a safety review for finance/trading tasks, experiments, or code execution.

## Required Agents (in sequence)
1. ORCHESTRATOR - Classify task and identify if safety review needed
2. SAFETY - Enforce project safety boundaries
3. [Optional: CODE REVIEW] - If reviewing code changes
4. [Optional: DATA REVIEW] - If reviewing data or experiments
5. FINAL ACCEPTANCE - Verify safety review completion

## Workflow Instructions
1. Start with `/summon-orchestrator` and provide the task to review
2. Wait for orchestrator to classify task and determine if safety review is required
3. Invoke `/summon-safety` with the task description or code to review
4. If reviewing code changes, invoke `/summon-code-review` after safety review
5. If reviewing data or experiments, invoke `/summon-data-review` after safety review
6. End with `/summon-final-acceptance` to verify completion

## Sign-off Requirements
- Safety Agent must provide PASS or BLOCKED / NEEDS_HUMAN_APPROVAL
- If used, Code Review Agent must provide PASS or NEEDS_FIXES
- If used, Data Review Agent must provide PASS or NEEDS_FIXES
- Final Acceptance Agent must be PASS

## When to Use
- Every finance/trading task
- Every experiment
- Every code execution
- Any task involving credentials, APIs, external providers, model files, runtime code, or production behavior
- Default forbidden actions unless explicitly approved:
  * No live trading
  * No broker APIs
  * No order execution logic
  * No live alerts
  * No backtests unless explicitly authorized
  * No validation unless explicitly authorized
  * No P&L unless explicitly authorized
  * No profitability claims
  * No strategy mutation
  * No canonical_runtime changes
  * No .pkl/model artifact changes
  * No secrets exposure
  * No restricted/private endpoint scraping