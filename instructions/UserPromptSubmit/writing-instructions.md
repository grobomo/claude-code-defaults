---
id: writing-instructions
name: Writing Instructions
keywords: [instruction, keyword, keywords, trigger, match, matching, rule, rules, meta, write, create, add, new, frontmatter, why]
enabled: true
priority: 10
---

# Writing Instructions

## WHY This Exists

Instructions use keyword matching to load contextual rules. Bad keywords mean rules never fire. This meta-instruction ensures every instruction file is written correctly so the keyword system works reliably.

## Keyword Rules

1. **Single words only** - never hyphenated phrases like `getting-started` or `how-it-works`
   - Split into separate words: `getting`, `started`, `how`, `works`
   - User types natural language, not kebab-case

2. **Short words the user would actually type** - think about what triggers the prompt
   - Good: `bash`, `script`, `write`, `js`
   - Bad: `bash-scripting-safety`, `javascript-heredoc-pattern`

3. **Include verb forms** - `write`, `writing`, `create`, `add`, `edit`, `fix`, `debug`

4. **Include synonyms** - `docs` AND `documentation`, `repo` AND `repository`

5. **No redundant keywords** - if `mcp` covers it, don't also add `mcp-server`, `mcp-management`

6. **5-15 keywords per instruction** - fewer than 5 = too narrow, more than 15 = too noisy

## Frontmatter Format

```yaml
---
id: kebab-case-id
name: Human Readable Name
keywords: [word1, word2, word3]
enabled: true
priority: 10
---
```

- `id` matches filename (without .md)
- `priority` default 10, use 100 for critical rules (like review-instructions)
- `enabled` defaults to true

## Content Structure

Every instruction MUST have:

1. **Title** - `# Short Name`
2. **WHY** section - why this rule exists (not just what to do)
3. **What To Do** - concrete actions
4. **Do NOT** (optional) - common mistakes to avoid

## Where Instructions Live

Single location: `~/.claude/instructions/UserPromptSubmit/`

instruction-manager reads/writes here directly. No copies elsewhere.

## Keyword Selection Process

When creating a new instruction, review the current chat history to find what words the user actually typed that should have triggered this instruction. Those words become keywords.

1. **Look at what the user typed** - the exact words from the conversation that led to needing this instruction
2. **Be generous** - better to match too often than miss when needed
3. **Check existing instructions** - run `ls ~/.claude/instructions/UserPromptSubmit/` to see what's already covered

## Keywords vs Patterns

- **Keywords** = single words for UserPromptSubmit matching (user input). Use when a word in the user's prompt should load context.
- **Patterns** = regex for Stop hook response matching (Claude's output). Use when Claude's response text should trigger correction. **Patterns are preferred** -- they catch the exact bad behavior. Only use keywords when the trigger is user input, not Claude output.
- NEVER use multi-word keywords. Use patterns for phrase matching.
- `add_item()` auto-sanitizes: splits multi-word and hyphenated keywords into singles.

## Diagnosing Instruction Failures

When a Stop instruction should have fired but didn't:

1. **Hook never triggered** -> the **pattern** doesn't match Claude's output. Fix the pattern regex, not the instruction text. Find the exact phrase Claude wrote and add it to the pattern.
2. **Hook triggered but Claude ignored** -> the **instruction text** is unclear or missing the case. Fix the instruction body.
3. **Don't add new instructions** for what an existing pattern should catch -- widen the pattern instead. Avoid instruction bloat.

## Do NOT

- Do NOT use multi-word or hyphenated keywords (enforced by `_sanitize_keywords()`)
- Do NOT put instructions in CLAUDE.md (use instruction files)
- Do NOT create hooks when an instruction would work
- Do NOT skip the WHY section
- Do NOT maintain duplicate copies of instructions anywhere
