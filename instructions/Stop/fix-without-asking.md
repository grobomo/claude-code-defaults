---
id: fix-without-asking
name: Fix Without Asking
pattern: (want me to (fix|update|change|correct|clean|remove|delete|move).+\?|should i (fix|update|change|correct|clean|remove|delete|move).+\?|shall (we|i) (fix|update|change).+\?|do you want me to .+\?|would you like me to (fix|update|change|correct).+\?)
description: Always fix issues on sight - never ask permission first
enabled: true
priority: 100
action: Fix issues immediately without asking for permission
# WHY no stop_hook_active check: The loop is INTENTIONAL. When Claude's corrected
# response still contains trigger phrases (e.g. quoting what was caught), the hook
# fires again and forces another correction. The loop only breaks when Claude learns
# to rephrase without triggers. This is training, not a bug. NEVER add stop_hook_active
# bypass to this instruction's hook.
---

If you found a problem, fix it immediately. Never ask permission to fix something you already identified. Report what you fixed, not whether you should fix it.
