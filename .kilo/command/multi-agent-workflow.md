# Multi-Agent Workflow Command

## Purpose
Execute the full multi-agent workflow for complex tasks requiring multiple specialist agents.

## Required Agents (in sequence)
1. ORCHESTRATOR - Classify task and assign required agents
2. PLANNING - Create safe execution plan
3. [Optional: WEB RESEARCH] - If external/current info needed
4. [Optional: SIMILARITY] - If comparative analysis or reuse needed
5. [Optional: ARCHITECTURE] - If touching multiple files or affecting runtime
6. CODING - Implement code changes (if code task)
7. CODE REVIEW - Review implementation
8. TESTING/QA - Verify behavior
9. [Optional: DATA REVIEW] - If outputs are data
10. SAFETY - Enforce safety boundaries
11. [Optional: DOCUMENTATION] - If report required
12. GIT/CHANGE MANAGEMENT - Track repository impact
13. FINAL ACCEPTANCE - Verify task completion

## Workflow Instructions
1. Start with `/summon-orchestrator` and provide the user task
2. Wait for orchestrator to classify task and assign required agents
3. For each required agent in sequence:
   - Invoke the appropriate summon command
   - Wait for the agent to complete and provide sign-off
   - Pass the agent's output to the next agent
4. End with `/summon-final-acceptance` to verify completion
5. Only the Final Acceptance Agent can mark the task complete

## Sign-off Requirements
- All required agents must provide their respective sign-offs
- No BLOCKED or NEEDS_FIXES status from any required agent
- Safety Agent must be PASS or confirm no safety review needed
- QA Agent must be PASS or NOT_EXECUTED_BY_POLICY with clear reason
- Final Acceptance Agent must be PASS

## When to Use
- Any multi-step task
- Any code modification
- Any experiment
- Any research plan
- Any repo workflow
- Any task that could affect project direction