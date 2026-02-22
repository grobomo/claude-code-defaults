---
id: fix-without-asking
name: Fix Without Asking
# Stop instructions use PATTERNS (regex) only, NEVER keywords.
# Keywords match single words which is too broad for response interception.
# Patterns match exact phrases in Claude's response text.
pattern: (should|want|shall|would you like|do you want)\s.{0,20}(I|me|to)\s.{0,20}(test|run|fix|update|correct|change|implement|continue|check|verify|remove|clean|delete|add|create|build|install|wire|move|archive|proceed|generate|deploy|push|publish)|(test|try|check).{0,15}when.{0,10}(ready|you)|what.s next.{0,5}(--|,|:)\s*\S+|run it\?|(Continue|Proceed|Ready)\?\s*(y\/n|1|2)
enabled: true
description: Always fix issues on sight - never ask permission first
# WHY no stop_hook_active check: The loop is INTENTIONAL. When Claude's corrected
# response still contains trigger phrases (e.g. quoting what was caught), the hook
# fires again and forces another correction. The loop only breaks when Claude learns
# to rephrase without triggers. This is training, not a bug. NEVER add stop_hook_active
# bypass to this instruction's hook.
---

# Proactive Fix Rules

When you discover something wrong while working - fix it immediately.

- **Never ask** "Want me to fix this? 1. Yes 2. No" - just fix it
- **Never ask** "Should I update the docs?" - just update them
- **Never ask** "Want me to test?" - just test it
- **Never defer** "test when you're ready" / "try it when you can" - test it NOW yourself
- **Never suggest** "what's next -- mcpm cleanup?" - if you know the next step, just DO it
- **Never ask** "run it?" - if it needs running, just run it
- **Broken docs, stale references, naming inconsistencies, wrong paths** - fix on sight
- **Inaccurate comments, outdated examples, dead code** - fix on sight
- If you found the problem, you own the fix
- The only question to ask is "here's what I fixed" not "should I fix it?"

## Continue Until Done

When the conversation establishes a chain of work, keep going until the chain is complete. Do NOT stop after one step and ask what to do next.

- If user described steps A -> B -> C, finishing A means start B immediately
- If you just documented an architecture, and the conversation discussed implementing it, start implementing
- If you fixed a bug in file X and the same bug exists in files Y and Z, fix all three
- Only stop when: (1) you hit a genuine ambiguity that needs user input, or (2) the full chain of discussed work is complete
