---
id: RULE-GUIDELINES
name: Rule Guidelines
keywords: [rule, guideline, keyword, frontmatter, write, create, new]
description: "WHY: Bad keywords mean rules never fire, wrong event type means wrong timing. WHAT: Master reference for rule creation"
enabled: true
priority: 5
action: Follow these guidelines when creating any rule or hook
min_matches: 1
---

# Rule Guidelines

## WHY This Exists

Rules use keyword matching to load contextual rules. Bad keywords mean rules never fire. Wrong hook event type means the rule fires at the wrong time (or not at all). This meta-rule ensures every rule file is written correctly and placed in the right event folder.

## Step 1: Choose the Correct Hook Event Type

**WHY this matters:** A rule in the wrong event folder either never fires or fires too late. A rule about blocking destructive Bash commands MUST be PreToolUse (before the tool runs), not UserPromptSubmit (before Claude even thinks about tools). Getting this wrong is the #1 rule bug.

| Ask yourself | Event type | Folder | Example |
|-------------|------------|--------|---------|
| Should Claude know this BEFORE processing the prompt? | UserPromptSubmit | `UserPromptSubmit/` | Routing rules, style preferences, tool selection |
| Should this BLOCK or MODIFY a tool call before it runs? | PreToolUse | `PreToolUse/` | Block `rm` commands, deny writes to deliverable/, require confirmation |
| Should this CHECK something after a tool finishes? | PostToolUse | `PostToolUse/` | Verify test output, log enforcement, mark suggestions fulfilled |
| Should this CHECK Claude's final response before sending? | Stop | `Stop/` | Catch "want me to?" questions, enforce action over asking |

### Decision Tree

```
Is this about BLOCKING or GATEKEEPING an action?
  YES -> PreToolUse (fires before Bash/Write/Edit/etc runs)
  NO  ->
    Is this about what Claude should KNOW while thinking?
      YES -> UserPromptSubmit (injected as context)
      NO  ->
        Is this about checking AFTER something happened?
          YES -> PostToolUse (fires after tool completes)
          NO  -> Stop (fires when Claude finishes responding)
```

### Hook Creation: Always Use hook-manager

**When a rule needs a hook, ALWAYS use the hook-manager skill.** Never write hooks manually or directly edit settings.json.

- **Official docs:** https://code.claude.com/docs/en/hooks
- **Hook-manager skill:** Has templates, correct stdin/stdout contracts, and registry management
- **Hook event reference:** See hook-manager SKILL.md for full event table, matcher rules, and Node.js templates

## Step 2: Write the Frontmatter

```yaml
---
id: kebab-case-id
name: Human Readable Name
keywords: [word1, word2, word3, word4, word5]
description: "WHY: <reason this exists>. WHAT: <what it enforces>."
enabled: true
priority: 10
action: Short TUI summary (max ~60 chars)
min_matches: 2
---
```

### Field Rules

- `id` matches filename (without .md)
- `priority` default 10, use 5 for critical meta-rules, 100 for advisory
- `enabled` defaults to true
- `action` **REQUIRED** - shown in TUI as `ACTION: ...`
- `description` **MUST include WHY** - not just what the rule does, but why it exists. Without WHY, rules become cargo cult.
- `min_matches` - how many keywords must match to trigger (default 2, see Step 3)

### Description WHY Requirement

Every rule `description` field must answer: "Why does this rule exist? What went wrong without it?"

| Bad (no WHY) | Good (has WHY) |
|-------------|---------------|
| `Prevent deletion of files` | `WHY: Deleted files are unrecoverable. WHAT: Archive to timestamped folder instead of deleting` |
| `Route to wiki-api skill` | `WHY: WebFetch fails on authenticated Confluence URLs. WHAT: Use wiki-api skill for wiki operations` |

## Step 3: Write Keywords (Threshold Matching System)

### How Matching Works

The rule loader uses **threshold matching**: it counts how many of a rule's keywords appear in the user's prompt, and the rule only fires if the count meets `min_matches`.

```
prompt: "scan my network for devices"
rule keywords: [scan, network, nmap, devices, hosts]
matches: scan, network, devices = 3 hits
min_matches: 2
result: FIRES (3 >= 2)
```

This prevents false positives from broad single words while still being flexible about phrasing.

### min_matches Field

| Value | When to use | Example |
|-------|-------------|---------|
| `min_matches: 2` | **Default.** Most rules. Requires 2+ keyword hits. | bash-scripting, mcp-management |
| `min_matches: 1` | Unique keywords that are unambiguous on their own. | URLs (`atlassian.net`), tool names (`winremote`), filenames (`claude.md`) |

**Omitting min_matches = default 2.** Only add `min_matches: 1` when the rule has keywords so specific they can't false-positive.

### Keyword Rules

1. **Single lowercase words** - never hyphenated phrases like `getting-started`
   - Split: `getting`, `started`
   - Users type natural language, not kebab-case
   - Exception: URLs and dotted names are OK as single keywords (`atlassian.net`, `claude.md`)

2. **Short words users actually type** - think about what the user would say
   - Good: `bash`, `script`, `network`, `scan`
   - Bad: `bash-scripting-safety`, `javascript-heredoc-pattern`

3. **Include verb forms** - `write`, `create`, `add`, `edit`, `fix`, `debug`

4. **Include synonyms** - `docs` AND `documentation`, `repo` AND `repository`

5. **No redundant keywords** - if `mcp` covers it, don't also add `server` (too broad alone)

6. **5-15 keywords per rule** - fewer = too narrow, more = too noisy

7. **Think in pairs** - since default min_matches is 2, keywords should form natural pairs that appear together in relevant prompts:
   - `[bash, script, heredoc, js, node, write]` -- "write a bash script" hits `write` + `bash` + `script`
   - `[mcpm, mcp, server, start, stop, add]` -- "start the mcp server" hits `start` + `mcp` + `server`

### Choosing min_matches

Ask: "Could any ONE of these keywords appear in an unrelated prompt?"

- YES -> `min_matches: 2` (default, omit from frontmatter)
- NO, keywords are unique enough -> `min_matches: 1`

Examples:

| Rule | Keywords | min_matches | Why |
|------|----------|-------------|-----|
| wiki-api-routing | `[atlassian, atlassian.net, confluence, wiki, page]` | 1 | `atlassian.net` only appears in wiki contexts |
| winremote-routing | `[winremote, remote, desktop, visual, control, ec2]` | 1 | `winremote` is unambiguous |
| bash-scripting | `[heredoc, bash, script, javascript, node, write, js]` | 2 | `write` or `bash` alone are too broad |
| mcp-management | `[mcpm, mcp, server, start, stop, add, install]` | 2 | `start` or `server` alone are too broad |
| no-modify-claudemd | `[claude.md, CLAUDE.md, edit, memo, update]` | 1 | `claude.md` is specific enough |

### Keyword Quality Review

Before finalizing:

1. **Review the chat** - what words did the user actually type?
2. **Consider false positives** - with min_matches: 2, will any pair of keywords match unrelated prompts?
3. **Test mentally** - 5 prompts that SHOULD trigger, 5 that SHOULD NOT
4. **Check existing rules** - `ls ~/.claude/rules/UserPromptSubmit/` for keyword overlap

## Step 4: Write the Content

Every rule MUST have:

1. **Title** - `# Short Name`
2. **WHY** section - why this rule exists (what went wrong without it)
3. **Rule** section - concrete actions
4. **Do NOT** (optional) - common mistakes to avoid

## Stop Hook Special Rules

Stop rules live in `~/.claude/rules/Stop/` and use regex patterns:

```yaml
pattern: (want me to .+\?|shall i .+\?)
```

- **ALWAYS use `pattern` (regex)** - NEVER use `keywords` field in Stop hooks
- Keywords are raw substring matches that false-positive on code, tables, and technical content
- `done` matches "undone", `all set` matches "all settings", `complete` matches "completely"
- Patterns support word boundaries (`\b`), anchors, and alternation (`|`)

### Verify Patterns Against Real Data

Before writing or modifying a Stop hook pattern:

1. **Session JSONL logs** - extract assistant text blocks:
   ```bash
   ls -t ~/.claude/projects/<project-slug>/*.jsonl | head -3
   ```

2. **Stop hook log** - check what actually fired:
   ```bash
   tail -50 ~/.claude/rules/stop-loader.log
   ```

## Where Rules Live

```
~/.claude/rules/
  UserPromptSubmit/   # Injected when prompt keywords match (threshold matching)
  Stop/               # Checked against Claude response text (regex patterns)
  PreToolUse/         # Checked before tool calls
  PostToolUse/        # Checked after tool calls
```

Single source of truth. No copies elsewhere.

## Do NOT

- Do NOT use multi-word hyphenated keywords (split them)
- Do NOT put rules in CLAUDE.md (use rule files)
- Do NOT create hooks without using hook-manager skill
- Do NOT skip the WHY section
- Do NOT skip WHY in the description field
- Do NOT maintain duplicate copies of rules anywhere
- Do NOT put PreToolUse rules in UserPromptSubmit (wrong timing)
- Do NOT put blocking/gatekeeping rules in UserPromptSubmit (use PreToolUse)
- Do NOT set min_matches: 1 unless keywords are truly unambiguous
