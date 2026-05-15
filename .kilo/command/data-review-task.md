# Data Review Task Command

## Purpose
Execute a data analysis task requiring data workflow review.

## Required Agents (in sequence)
1. ORCHESTRATOR - Classify task as data analysis
2. PLANNING - Create safe execution plan
3. DATA REVIEW - Review data workflows, CSVs, reports, manifests, schemas
4. [Optional: CODING] - If scripts are needed for data processing
5. QA - Verify behavior and outputs
6. SAFETY - Enforce safety boundaries (no profitability claims, etc.)
7. DOCUMENTATION - Create data analysis report
8. FINAL ACCEPTANCE - Verify task completion

## Workflow Instructions
1. Start with `/summon-orchestrator` and provide the data analysis task description
2. Wait for orchestrator to classify as data analysis task and assign agents
3. Invoke `/summon-planning` with the task description
4. Invoke `/summon-data-review` to review the data workflow
5. If scripts are needed for data processing, invoke `/summon-coding` with approved plan
6. Invoke `/summon-testing-qa` to verify behavior and outputs
7. Invoke `/summon-safety` to enforce boundaries (critical for data tasks)
8. Invoke `/summon-documentation` to create the data analysis report
9. End with `/summon-final-acceptance` to verify completion

## Sign-off Requirements
- Data Review Agent must provide PASS or NEEDS_FIXES
- If used, Coding Agent must provide PASS or NEEDS_MORE_WORK
- QA Agent must provide PASS or NEEDS_FIXES / NOT_EXECUTED_BY_POLICY
- Safety Agent must be PASS or confirm no safety review needed
- If used, Documentation Agent must provide PASS or NEEDS_FIXES
- Final Acceptance Agent must be PASS

## When to Use
- Data acquisition
- CSV analysis
- Reports
- Research outputs
- Market data
- Any experiment-like workflow
- Checking data inputs, schema consistency, row counts
- Ensuring descriptive analysis is not misrepresented as strategy performance