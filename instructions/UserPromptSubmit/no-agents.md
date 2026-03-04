---
keywords:
  - agent
  - task
  - subagent
  - explore
  - delegate
action: Do work directly instead of spawning Task agents
why: Task agents frequently hang and never complete, wasting time and blocking progress
---

# No Agent Delegation

Do NOT use the Task tool to spawn subagents. Agents frequently hang and never complete, which blocks progress and wastes the user's time. Do all work directly yourself using Read, Write, Edit, Bash, Glob, Grep, and other tools. This applies to ALL agent types including Explore, Plan, Bash agents, and general-purpose agents.
