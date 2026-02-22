---
id: background-tasks
name: Background Task Management
keywords: [background, parallel, async, deploy, build, zombie, task]
enabled: true
description: Background task management and zombie prevention
---

# Background Task Instructions

When starting background tasks:
1. **SAVE the returned task_id** immediately
2. Check progress with TaskOutput(task_id, block=false) periodically
3. Kill hung tasks (>2 min, no progress) with TaskStop using saved task_id
4. **Never leave zombie processes** - clean up before moving on

Use agents for tasks whenever possible to preserve context.
Perform independent tasks in parallel.
