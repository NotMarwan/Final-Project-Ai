# Code Task Command

## Purpose
Execute a code creation or modification task using the standard coding workflow.

## Required Agents (in sequence)
1. ORCHESTRATOR - Classify task as code creation/modification
2. PLANNING - Create safe execution plan
3. SIMILARITY - Find prior art and similar implementations
4. ARCHITECTURE - Design technical structure (if multiple files or runtime impact)
5. CODING - Implement code changes
6. CODE REVIEW - Review implementation
7. TESTING/QA - Verify behavior
8. SAFETY - Enforce safety boundaries
9. GIT/CHANGE MANAGEMENT - Track repository impact
10. FINAL ACCEPTANCE - Verify task completion

## Workflow Instructions
1. Start with `/summon-orchestrator` and provide the code task description
2. Wait for orchestrator to confirm this is a code task and assign agents
3. Invoke `/summon-planning` with the task description
4. Invoke `/summon-similarity` to find similar implementations
5. If the task touches multiple files or might affect runtime, invoke `/summon-architecture`
6. Invoke `/summon-coding` with the approved plan
7. Invoke `/summon-code-review` to review the implementation
8. Invoke `/summon-testing-qa` to verify behavior
9. Invoke `/summon-safety` to enforce boundaries
10. Invoke `/summon-git` to track changes
11. End with `/summon-final-acceptance` to verify completion

## Sign-off Requirements
All required agents must provide PASS status in their respective sign-off formats.

## When to Use
- Any code creation
- Any code edit
- Any script creation
- Any bug fix
- Any refactor