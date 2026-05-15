# Prompt Engineering Task Command

## Purpose
Execute a prompt engineering task to create precise prompts for other coding/research agents.

## Required Agents (in sequence)
1. ORCHESTRATOR - Classify task as prompt creation request
2. PROMPT ENGINEERING - Convert project goals into executable prompts
3. [Optional: SAFETY] - If task is risky (finance/trading, experiments, etc.)
4. FINAL ACCEPTANCE - Verify task completion

## Workflow Instructions
1. Start with `/summon-orchestrator` and provide the prompt creation request
2. Wait for orchestrator to classify as prompt creation task and assign agents
3. Invoke `/summon-prompt-engineering` with the specific goal or task for which a prompt is needed
4. If the task involves finance/trading, experiments, or other risky areas, invoke `/summon-safety` to review
5. End with `/summon-final-acceptance` to verify completion

## Sign-off Requirements
- Prompt Engineering Agent must provide PASS or NEEDS_FIXES
- If used, Safety Agent must be PASS or confirm no safety review needed
- Final Acceptance Agent must be PASS

## When to Use
- Any request to create prompts
- Roo Code prompts
- Gemini prompts
- Claude/OpenCode prompts
- Research-agent prompts
- Multi-agent workflow prompts
- Converting project goals into executable prompts with context, constraints, success criteria, etc.