# Agent Summoning System README

## Overview
This repository contains a multi-agent orchestrator system implemented through role-specific prompt files. Agents are "summoned" by assigning them specific roles through their instruction files.

## How Agents Work in This System
- **Agents are not separate processes** - they are role definitions that guide the AI assistant
- **To summon an agent**: Read its instruction file and act as that agent for the current task
- **Each agent has**: A specific role, responsibilities, output format, and sign-off requirements
- **No agent can mark a task complete** - only the Final Acceptance Agent can do that

## How to Summon Agents Manually

### Method 1: Role Assignment
1. Read the agent's instruction file: `.kilo/agent/NN_name.md`
2. Tell yourself: "I am now the [AGENT NAME] agent"
3. Follow the responsibilities and output format in that file
4. When done, provide your sign-off in the required format
5. Wait for the next agent in the workflow or Final Acceptance

### Method 2: Using Command Files
1. Read the command file: `.kilo/command/summon-agentname.md`
2. The command file tells you:
   - Which agent role to assume
   - Which instruction file to read
   - What output format to follow
   - What not to do (role boundaries)

## Agent Instruction Files Location
All agent definitions are in `.kilo/agent/`:
- `01_orchestrator_agent.md` - Task classification and workflow management
- `02_planning_agent.md` - Safe execution planning
- `03_web_research_agent.md` - External information gathering
- `04_similarity_agent.md` - Prior art and pattern finding
- `05_architecture_agent.md` - Technical structure design
- `06_coding_agent.md` - Code implementation
- `07_code_review_agent.md` - Code change review
- `08_testing_qa_agent.md` - Behavior verification
- `09_data_review_agent.md` - Data/workflow review
- `10_safety_compliance_agent.md` - Safety boundary enforcement
- `11_documentation_agent.md` - Documentation creation
- `12_git_change_mgmt_agent.md` - Repository change tracking
- `13_security_agent.md` - Security risk review
- `14_prompt_engineering_agent.md` - Prompt creation
- `15_final_acceptance_agent.md` - Task completion verification

## Command Files Location
All summon commands are in `.kilo/command/`:
- Individual agent commands: `summon-*.md`
- Workflow commands: `multi-agent-workflow.md`, `code-task.md`, `research-task.md`, etc.

## Workflow Principles
1. **Orchestrator First** - Always start with the Orchestrator to classify the task
2. **Role Boundaries** - Each agent only performs their specific duties
3. **Sequential Processing** - Agents typically work in a defined sequence
4. **Safety and QA Gates** - Safety and QA agents review work before completion
5. **Final Acceptance** - Only the Final Acceptance Agent can mark tasks complete

## Typical Workflow Sequences

### Simple Task
```
ORCHESTRATOR → [REQUIRED AGENTS] → SAFETY → QA → FINAL ACCEPTANCE
```

### Code Task
```
ORCHESTRATOR → PLANNING → SIMILARITY → ARCHITECTURE → CODING → 
CODE REVIEW → QA → SAFETY → GIT → FINAL ACCEPTANCE
```

### Research Task
```
ORCHESTRATOR → WEB RESEARCH → [SIMILARITY] → DOCUMENTATION → FINAL ACCEPTANCE
```

### Safety Review
```
ORCHESTRATOR → SAFETY → [CODE REVIEW/DATA REVIEW] → FINAL ACCEPTANCE
```

## Important Rules
1. **No agent should be considered “complete” without the required sign-off**
2. **Agents must not exceed their defined role**
3. **Only Final Acceptance Agent can mark task complete**
4. **All required agents must provide PASS status for task completion**
5. **Complex tasks must go through Orchestrator → required role agents → Safety/QA → Final Acceptance**
6. **No trading logic, backtests, P&L calculations, or canonical_runtime modifications without explicit approval**

## Current Status
- ✅ Agent definition files created (15 agents)
- ✅ Command files created (individual + workflow commands)
- ⚠️ This README file (you are reading it)
- ❌ No project tasks executed yet
- ❌ No agents actually summoned for real work
- ❌ No files changed outside of `.kilo/`

## Next Step
Wait for a user task, then use the orchestrator command (`/summon-orchestrator`) to decide which agents are required for that specific task.

Remember: The agents are simulated by you reading their instructions and role-playing their responsibilities. The true power comes from following the defined workflow and respecting role boundaries.