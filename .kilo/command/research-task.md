# Research Task Command

## Purpose
Execute a research task requiring current external information.

## Required Agents (in sequence)
1. ORCHESTRATOR - Classify task as research requiring current info
2. WEB RESEARCH - Search for current external information
3. [Optional: SIMILARITY] - If comparative analysis needed
4. DOCUMENTATION - Create research report (if report needed)
5. FINAL ACCEPTANCE - Verify task completion

## Workflow Instructions
1. Start with `/summon-orchestrator` and provide the research question
2. Wait for orchestrator to classify as research task requiring current info
3. Invoke `/summon-web-research` with the specific research question
4. If comparative information is needed, invoke `/summon-similarity`
5. If a report is required, invoke `/summon-documentation` to create the research report
6. End with `/summon-final-acceptance` to verify completion

## Sign-off Requirements
- Web Research Agent must provide PASS or NEEDS_MORE_WORK
- If used, Similarity Agent must provide PASS or NEEDS_MORE_WORK
- If used, Documentation Agent must provide PASS or NEEDS_FIXES
- Final Acceptance Agent must be PASS

## When to Use
- Latest libraries, APIs, frameworks, tools, regulations, model behavior, pricing, docs, benchmarks
- Any unfamiliar term, tool, model, error, or external service
- Any question involving current availability, capacity, limits, or real-world status