"""
analyze_effectiveness.py - Full super-manager pipeline effectiveness analyzer.

Parses ALL log sources across the hook pipeline:
  1. UserPromptSubmit: rule loader (loader.log), skill matcher, MCP matcher (hooks.log)
  2. PreToolUse: enforcement gate (enforcement.log)
  3. PostToolUse: skill usage tracker (skill-usage.jsonl), enforcement fulfillment
  4. Stop: stop rule patterns (stop-loader.log) vs assistant messages (JSONL)

Outputs: markdown report + styled HTML dashboard (auto-opened in browser).

Usage:
    python super_manager.py analyze [--session <path>] [--verbose] [--html] [--diagram]
"""
import sys
import os
import json
import re
import datetime
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared.configuration_paths import (
    ANALYSIS_REPORT, STOP_LOADER_LOG, STOP_RULES_DIR,
    PROJECTS_DIR, LOGS_DIR, REPORTS_DIR, RULES_BASE, HOOKS_DIR,
)
from shared.file_operations import atomic_write, ensure_directory
from shared.logger import create_logger

log = create_logger("analyze-effectiveness")

HTML_REPORT = os.path.join(REPORTS_DIR, "effectiveness-dashboard.html")
RULE_LOADER_LOG = os.path.join(RULES_BASE, "loader.log")
HOOKS_LOG = os.path.join(HOOKS_DIR, "hooks.log")

# ===================================================================
# JSONL parsing
# ===================================================================

def _find_latest_session():
    if not os.path.isdir(PROJECTS_DIR):
        return None
    best_path, best_mtime = None, 0
    for slug_dir in os.listdir(PROJECTS_DIR):
        slug_path = os.path.join(PROJECTS_DIR, slug_dir)
        if not os.path.isdir(slug_path):
            continue
        for fname in os.listdir(slug_path):
            if not fname.endswith(".jsonl"):
                continue
            fpath = os.path.join(slug_path, fname)
            mtime = os.path.getmtime(fpath)
            if mtime > best_mtime:
                best_mtime = mtime
                best_path = fpath
    return best_path


def extract_assistant_messages(jsonl_path):
    messages = []
    if not jsonl_path or not os.path.isfile(jsonl_path):
        return messages
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if entry.get("type") != "assistant":
                continue
            msg = entry.get("message", {})
            for part in msg.get("content", []):
                if part.get("type") == "text":
                    messages.append({"text": part["text"], "index": len(messages)})
    return messages


# ===================================================================
# Stop hook loading (pattern extraction from .md files)
# ===================================================================

def _parse_frontmatter(content):
    if not content.startswith("---"):
        return {}
    end = content.find("---", 3)
    if end == -1:
        return {}
    fm_block = content[3:end].strip()
    meta = {}
    for line in fm_block.split("\n"):
        line = line.strip()
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if val.lower() in ("true", "false"):
            val = val.lower() == "true"
        meta[key] = val
    return meta


def load_stop_hooks(stop_dir=None):
    stop_dir = stop_dir or STOP_RULES_DIR
    hooks = []
    if not os.path.isdir(stop_dir):
        return hooks
    for fname in sorted(os.listdir(stop_dir)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(stop_dir, fname)
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        meta = _parse_frontmatter(content)
        if not meta.get("id"):
            continue
        if meta.get("enabled") is False:
            continue
        pattern = meta.get("pattern", "")
        compiled = None
        if pattern:
            try:
                compiled = re.compile(pattern, re.IGNORECASE)
            except re.error:
                log.warn(f"Bad regex in {fname}: {pattern}")
        hooks.append({
            "id": meta["id"], "file": fname, "pattern": pattern,
            "regex": compiled, "priority": int(meta.get("priority", 10)),
            "name": meta.get("name", meta["id"]),
        })
    return hooks


# ===================================================================
# MODULE 1: Stop hook pattern analysis (patterns vs assistant messages)
# ===================================================================

def analyze_stop_hooks(hooks, messages):
    results = {}
    for hook in hooks:
        results[hook["id"]] = {
            "id": hook["id"], "name": hook["name"], "pattern": hook["pattern"],
            "fires": 0, "matched_messages": [], "matched_previews": [],
        }
    for msg in messages:
        text = msg["text"]
        for hook in hooks:
            if not hook["regex"]:
                continue
            m = hook["regex"].search(text)
            if m:
                r = results[hook["id"]]
                r["fires"] += 1
                r["matched_messages"].append(msg["index"])
                preview = text[max(0, m.start() - 20):m.end() + 20].replace("\n", " ")
                r["matched_previews"].append(preview[:80])
    total = len(messages)
    for r in results.values():
        r["fire_rate"] = (r["fires"] / total * 100) if total else 0
    return results


# ===================================================================
# MODULE 2: Stop-loader.log parsing (actual blocks/allows/storms)
# ===================================================================

def analyze_stop_log(log_path=None):
    log_path = log_path or STOP_LOADER_LOG
    stats = {
        "total_events": 0, "blocks": 0, "allows": 0, "no_message": 0,
        "per_hook": defaultdict(int), "storms": [], "hourly": defaultdict(int),
    }
    if not os.path.isfile(log_path):
        stats["error"] = f"Log not found: {log_path}"
        return stats

    recent_fires = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            stats["total_events"] += 1
            ts = None
            try:
                ts = datetime.datetime.fromisoformat(line[:26].rstrip())
                stats["hourly"][ts.strftime("%Y-%m-%d %H:00")] += 1
            except (ValueError, IndexError):
                pass

            if "BLOCKING" in line:
                stats["blocks"] += 1
                hook_matches = re.findall(r'(\w[\w-]+)\s*\("pattern:', line)
                if not hook_matches:
                    hook_matches = re.findall(r'pattern hit -> (\S+?)\.md', line)
                for hid in hook_matches:
                    stats["per_hook"][hid] += 1
                    if ts:
                        recent_fires.append((ts, hid))
            elif "allowing stop" in line:
                stats["allows"] += 1
            if "no last_assistant_message" in line:
                stats["no_message"] += 1
            hit_match = re.search(r'pattern hit -> (\S+?)\.md', line)
            if hit_match and "BLOCKING" not in line:
                hid = hit_match.group(1)
                stats["per_hook"][hid] += 1
                if ts:
                    recent_fires.append((ts, hid))

    # Storm detection: same hook 3+ times in 5 seconds
    recent_fires.sort()
    i = 0
    while i < len(recent_fires):
        ts_i, hid_i = recent_fires[i]
        burst = [(ts_i, hid_i)]
        j = i + 1
        while j < len(recent_fires):
            ts_j, hid_j = recent_fires[j]
            if hid_j == hid_i and (ts_j - ts_i).total_seconds() <= 5:
                burst.append((ts_j, hid_j))
                j += 1
            else:
                break
        if len(burst) >= 3:
            stats["storms"].append({
                "hook": hid_i, "count": len(burst),
                "start": burst[0][0].isoformat(), "end": burst[-1][0].isoformat(),
            })
        i = j if j > i + 1 else i + 1
    return stats


# ===================================================================
# MODULE 3: Rule loader analysis (UserPromptSubmit keyword triggers)
# ===================================================================

def analyze_rule_loader(log_path=None):
    """Parse loader.log for rule trigger frequency, keyword accuracy, cache behavior."""
    log_path = log_path or RULE_LOADER_LOG
    stats = {
        "total_triggers": 0, "loaded": 0, "cached": 0,
        "per_rule": defaultdict(lambda: {"loaded": 0, "cached": 0, "keywords_hit": defaultdict(int)}),
        "per_keyword": defaultdict(int),
        "per_prompt_rule_count": [],  # how many rules fire per prompt
    }
    if not os.path.isfile(log_path):
        stats["error"] = f"Log not found: {log_path}"
        return stats

    current_prompt = None
    current_prompt_rules = 0

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # Format: 2026-03-01 18:53:55 [KEYWORD] trigger="prompt..." match="keyword" -> path (loaded|cached)
            m = re.search(r'\[KEYWORD\] trigger="(.{0,60})" match="([^"]*)" -> .*?([^/\\]+)\.md \((loaded|cached)\)', line)
            if not m:
                continue
            stats["total_triggers"] += 1
            trigger_text = m.group(1)
            keyword = m.group(2)
            rule_file = m.group(3)
            state = m.group(4)

            if state == "loaded":
                stats["loaded"] += 1
                stats["per_rule"][rule_file]["loaded"] += 1
            else:
                stats["cached"] += 1
                stats["per_rule"][rule_file]["cached"] += 1

            stats["per_rule"][rule_file]["keywords_hit"][keyword] += 1
            stats["per_keyword"][keyword] += 1

    return stats


# ===================================================================
# MODULE 4: Skill/MCP matcher analysis (from hooks.log)
# ===================================================================

def analyze_skill_mcp_matcher(log_path=None):
    """Parse hooks.log for skill-mcp-claudemd-injector entries."""
    log_path = log_path or HOOKS_LOG
    stats = {
        "total_prompts": 0,
        "skill_matches": 0, "mcp_matches": 0,
        "no_skill_match": 0, "no_mcp_match": 0,
        "per_skill_matched": defaultdict(int),
        "per_mcp_matched": defaultdict(int),
        "enforcement_writes": 0,
        "avg_skills_per_prompt": 0,
        "skills_per_prompt_counts": [],
    }
    if not os.path.isfile(log_path):
        stats["error"] = f"Log not found: {log_path}"
        return stats

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            if "[skill-mcp-claudemd-injector:" not in line:
                continue

            # Skill matches: "matched N skills (no inject): skill1, skill2"
            sm = re.search(r'\[skill-mcp-claudemd-injector:skill\] matched (\d+) skills.*?: (.+)', line)
            if sm:
                count = int(sm.group(1))
                names = [s.strip() for s in sm.group(2).split(",")]
                stats["skill_matches"] += 1
                stats["skills_per_prompt_counts"].append(count)
                for name in names:
                    if name:
                        stats["per_skill_matched"][name] += 1
                continue

            # No skill match
            if "no skills matched" in line and "skill-mcp-claudemd-injector:skill" in line:
                stats["no_skill_match"] += 1
                stats["skills_per_prompt_counts"].append(0)
                continue

            # MCP matches: "suggested N MCPs: mcp1, mcp2"
            mm = re.search(r'\[skill-mcp-claudemd-injector:mcp\] suggested (\d+) MCPs?: (.+)', line)
            if mm:
                names = [s.strip() for s in mm.group(2).split(",")]
                stats["mcp_matches"] += 1
                for name in names:
                    if name:
                        stats["per_mcp_matched"][name] += 1
                continue

            # No MCP match
            if "no MCPs matched" in line and "skill-mcp-claudemd-injector:mcp" in line:
                stats["no_mcp_match"] += 1
                continue

            # Enforcement writes
            if "wrote pending suggestions" in line:
                stats["enforcement_writes"] += 1

    stats["total_prompts"] = stats["skill_matches"] + stats["no_skill_match"]
    if stats["skills_per_prompt_counts"]:
        stats["avg_skills_per_prompt"] = sum(stats["skills_per_prompt_counts"]) / len(stats["skills_per_prompt_counts"])
    return stats


# ===================================================================
# MODULE 5: Enforcement log (PreToolUse gate)
# ===================================================================

def analyze_enforcement(log_path=None):
    log_path = log_path or os.path.join(LOGS_DIR, "super-manager-enforcement.log")
    stats = {
        "total": 0, "blocked": 0, "soft_warned": 0, "fulfilled": 0,
        "per_skill": defaultdict(lambda: {"suggested": 0, "fulfilled": 0}),
        "per_tool_blocked": defaultdict(int),
    }
    if not os.path.isfile(log_path):
        stats["error"] = f"Log not found: {log_path}"
        return stats

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            stats["total"] += 1

            if "BLOCKED" in line and "SOFT" not in line:
                stats["blocked"] += 1
                tool_m = re.search(r'tool=(\S+)', line)
                if tool_m:
                    stats["per_tool_blocked"][tool_m.group(1)] += 1
            elif "SOFT_WARNED" in line:
                stats["soft_warned"] += 1
                tool_m = re.search(r'tool=(\S+)', line)
                if tool_m:
                    stats["per_tool_blocked"][tool_m.group(1)] += 1
            elif "FULFILLED" in line:
                stats["fulfilled"] += 1

            # Count per-skill suggestions from BLOCKED/SOFT_WARNED lines
            uf_match = re.search(r'unfulfilled=(\S+)', line)
            if uf_match:
                for s in uf_match.group(1).split(","):
                    s = s.strip()
                    if s:
                        stats["per_skill"][s]["suggested"] += 1
            # Count per-skill fulfillments from FULFILLED lines
            # Format: FULFILLED skill=hook-manager prompt="..."
            if "FULFILLED" in line:
                skill_m = re.search(r'skill=(\S+)', line)
                if skill_m:
                    stats["per_skill"][skill_m.group(1)]["fulfilled"] += 1
    return stats


# ===================================================================
# MODULE 6: Skill usage (PostToolUse tracker)
# ===================================================================

def analyze_skill_usage(log_path=None):
    log_path = log_path or os.path.join(LOGS_DIR, "skill-usage.jsonl")
    stats = {"total": 0, "by_skill": defaultdict(lambda: {"count": 0, "via": set()})}
    if not os.path.isfile(log_path):
        stats["error"] = f"Log not found: {log_path}"
        return stats
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            stats["total"] += 1
            skill = entry.get("skill", "unknown")
            tool = entry.get("tool", "unknown")
            stats["by_skill"][skill]["count"] += 1
            stats["by_skill"][skill]["via"].add(tool)
    return stats


# ===================================================================
# MODULE 7: Pattern overlap (Stop hooks)
# ===================================================================

def detect_overlap(hooks, messages):
    overlaps = []
    for msg in messages:
        text = msg["text"]
        fired = []
        for hook in hooks:
            if hook["regex"] and hook["regex"].search(text):
                fired.append(hook["id"])
        if len(fired) >= 2:
            overlaps.append({
                "index": msg["index"], "hooks": fired,
                "preview": text[:100].replace("\n", " "),
            })
    return overlaps


# ===================================================================
# MODULE 8: Recommendations (all modules)
# ===================================================================

def generate_recommendations(hook_results, stop_stats, overlaps, messages,
                             rule_loader, skill_mcp, enforcement, skill_usage):
    recs = []
    total_msgs = max(len(messages), 1)

    # ---------------------------------------------------------------
    # 1. BROAD KEYWORD OVERLAP: multiple rules triggered by same keyword
    # ---------------------------------------------------------------
    kw_to_rules = defaultdict(list)
    for rule_id, data in rule_loader.get("per_rule", {}).items():
        for kw, count in data.get("keywords_hit", {}).items():
            if count > 50:
                kw_to_rules[kw].append((rule_id, count))
    for kw, rules in kw_to_rules.items():
        if len(rules) >= 3:
            rules_sorted = sorted(rules, key=lambda x: -x[1])
            names = ", ".join(f"{r[0]} ({r[1]}x)" for r in rules_sorted[:4])
            total_waste = sum(r[1] for r in rules_sorted)
            recs.append({"severity": "HIGH", "component": "Rules", "hook": f"keyword '{kw}'",
                         "issue": f"{len(rules)} rules share keyword '{kw}' ({total_waste:,} total triggers): {names}",
                         "action": f"Remove '{kw}' from most rules or merge overlapping rules. Each match injects context tokens.",
                         "section": "rules"})

    # Single-rule broad keywords (>500 triggers)
    for rule_id, data in rule_loader.get("per_rule", {}).items():
        total_hits = data["loaded"] + data["cached"]
        if total_hits > 500:
            top_kw = max(data["keywords_hit"].items(), key=lambda x: x[1], default=("?", 0))
            recs.append({"severity": "WARN", "component": "Rules", "hook": rule_id,
                         "issue": f"Triggered {total_hits:,}x (top keyword: '{top_kw[0]}' {top_kw[1]:,}x)",
                         "action": f"Keyword '{top_kw[0]}' is too broad -- fires on unrelated prompts. Replace with 2-word combo or more specific term.",
                         "section": "rules"})

    # ---------------------------------------------------------------
    # 2. SKILL MATCHES >80% OF PROMPTS: keyword noise
    # ---------------------------------------------------------------
    total_prompts = max(skill_mcp.get("total_prompts", 1), 1)
    noisy_skills = []
    for name, count in skill_mcp.get("per_skill_matched", {}).items():
        match_rate = count / total_prompts * 100
        if match_rate > 80:
            noisy_skills.append((name, count, match_rate))
    if noisy_skills:
        noisy_skills.sort(key=lambda x: -x[2])
        names = ", ".join(f"{s[0]} ({s[2]:.0f}%)" for s in noisy_skills[:5])
        recs.append({"severity": "HIGH", "component": "Skills", "hook": "skill-matcher",
                     "issue": f"{len(noisy_skills)} skills match >80% of prompts: {names}",
                     "action": "These keywords are so broad they match everything. The matches are noise, not signal. Narrow keywords in SKILL.md or skill-registry.json.",
                     "section": "skills"})

    # Avg skills per prompt too high
    if skill_mcp.get("avg_skills_per_prompt", 0) > 6:
        recs.append({"severity": "WARN", "component": "Skills", "hook": "skill-matcher",
                     "issue": f"Avg {skill_mcp['avg_skills_per_prompt']:.1f} skills matched per prompt",
                     "action": "Most matches are false positives wasting enforcement gate checks. Tighten SKILL.md keywords.",
                     "section": "skills"})

    # ---------------------------------------------------------------
    # 3. LOW FULFILLMENT RATE: enforcement suggests but Claude ignores
    # ---------------------------------------------------------------
    enf_total = enforcement.get("total", 0)
    enf_fulfilled = enforcement.get("fulfilled", 0)
    enf_warned = enforcement.get("soft_warned", 0)
    if enf_total > 100:
        fulfill_rate = enf_fulfilled / max(enf_total, 1) * 100
        if fulfill_rate < 5:
            recs.append({"severity": "HIGH", "component": "Enforcement", "hook": "enforcement-gate",
                         "issue": f"Fulfillment rate {fulfill_rate:.1f}% ({enf_fulfilled:,} fulfilled / {enf_total:,} checks). "
                                  f"{enf_warned:,} soft warnings are being ignored.",
                         "action": "Either (a) skill suggestions don't match real intent, or (b) Claude bypasses them. "
                                   "Review top unfulfilled skills below -- remove wrong suggestions or make enforcement stricter.",
                         "section": "enforcement"})

    # ---------------------------------------------------------------
    # 4. TOP UNFULFILLED SKILLS: suggested many times, never used
    #    Only show top 5 worst offenders (highest suggestion count with zero use)
    # ---------------------------------------------------------------
    skill_usage_names = set(skill_usage.get("by_skill", {}).keys())
    unfulfilled_candidates = []
    for skill_id, data in enforcement.get("per_skill", {}).items():
        sug = data["suggested"]
        ful = data["fulfilled"]
        if sug > 500 and ful < 5 and skill_id not in skill_usage_names:
            unfulfilled_candidates.append((skill_id, sug, ful))
    # Sort by suggestion count descending, take top 5
    for skill_id, sug, ful in sorted(unfulfilled_candidates, key=lambda x: -x[1])[:5]:
        recs.append({"severity": "WARN", "component": "Enforcement", "hook": skill_id,
                     "issue": f"Suggested {sug:,}x but fulfilled {ful}x (never actually invoked via Skill/Task tool)",
                     "action": f"'{skill_id}' keywords match prompts but Claude never uses it. Either remove it from suggestions or make it more discoverable.",
                     "section": "enforcement-detail"})

    # ---------------------------------------------------------------
    # 5. STOP RULE EFFECTIVENESS
    # ---------------------------------------------------------------
    for hid, r in hook_results.items():
        rate = r["fire_rate"]
        if rate > 20:
            recs.append({"severity": "HIGH", "component": "Stop", "hook": hid,
                         "issue": f"Fire rate {rate:.1f}% -- pattern matches >1 in 5 responses",
                         "action": f"Tighten pattern or add word boundaries. Current: {r['pattern'][:60]}",
                         "section": "stop"})

    for storm in stop_stats.get("storms", []):
        recs.append({"severity": "WARN", "component": "Stop", "hook": storm["hook"],
                     "issue": f"Blocking storm: {storm['count']}x in <5s",
                     "action": "Pattern matches retry text -- Claude keeps hitting the same rule on retries.",
                     "section": "stop"})

    # Stop hooks with high all-time but 0 session fires
    for hid, r in hook_results.items():
        log_fires = stop_stats["per_hook"].get(hid, 0)
        if log_fires > 20 and r["fires"] == 0:
            recs.append({"severity": "INFO", "component": "Stop", "hook": hid,
                         "issue": f"{log_fires} all-time fires but 0 this session -- pattern may have trained Claude's behavior",
                         "action": "Good sign: Claude learned to avoid this pattern. Verify by checking recent sessions.",
                         "section": "stop"})

    # Stop hooks that NEVER fire
    for hid, r in hook_results.items():
        log_fires = stop_stats["per_hook"].get(hid, 0)
        if log_fires == 0 and r["fires"] == 0:
            recs.append({"severity": "INFO", "component": "Stop", "hook": hid,
                         "issue": "Never fired (0 all-time, 0 session)",
                         "action": "Either the pattern is broken or Claude never triggers this behavior. Test with a deliberate prompt.",
                         "section": "stop"})

    # Overlaps
    seen_pairs = set()
    for ov in overlaps:
        pair = tuple(sorted(ov["hooks"][:2]))
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            count = len([o for o in overlaps if set(pair).issubset(set(o["hooks"]))])
            recs.append({"severity": "WARN", "component": "Stop", "hook": f"{pair[0]} + {pair[1]}",
                         "issue": f"Both fire on {count} messages -- double-blocking same response",
                         "action": "Consider merging patterns or making them mutually exclusive.",
                         "section": "stop"})

    # ---------------------------------------------------------------
    # 6. SUGGESTED-BUT-NEVER-USED MCP SERVERS
    # ---------------------------------------------------------------
    for mcp_name, count in skill_mcp.get("per_mcp_matched", {}).items():
        if count > 100 and mcp_name not in skill_usage_names:
            recs.append({"severity": "INFO", "component": "MCP", "hook": mcp_name,
                         "issue": f"Suggested {count:,}x but never invoked via MCP tools",
                         "action": f"Either '{mcp_name}' keywords are too broad or Claude doesn't know how to use it. Review servers.yaml keywords.",
                         "section": "skills"})

    # ---------------------------------------------------------------
    # 7. RULE + SKILL KEYWORD COLLISION
    # ---------------------------------------------------------------
    rule_kws = set()
    for data in rule_loader.get("per_rule", {}).values():
        rule_kws.update(data.get("keywords_hit", {}).keys())
    skill_kws = set()
    for name in skill_mcp.get("per_skill_matched", {}).keys():
        # Skill names often correlate to keywords
        skill_kws.add(name.lower().replace("-", " "))
    # Check for high-frequency keywords that appear in both
    for kw in rule_loader.get("per_keyword", {}):
        kw_count = rule_loader["per_keyword"][kw]
        # Check if same keyword also triggers skills
        for skill_name, skill_count in skill_mcp.get("per_skill_matched", {}).items():
            if kw in skill_name.lower().replace("-", " ").split() and kw_count > 200 and skill_count > 1000:
                recs.append({"severity": "INFO", "component": "Rules+Skills", "hook": f"'{kw}' keyword",
                             "issue": f"Keyword '{kw}' triggers both rule loading ({kw_count:,}x) and skill matching ({skill_name}: {skill_count:,}x)",
                             "action": "Double context injection: rule content + skill suggestion for same keyword. May be redundant.",
                             "section": "rules"})
                break  # One rec per keyword

    # Sort: HIGH first, then WARN, then INFO
    severity_order = {"HIGH": 0, "WARN": 1, "INFO": 2}
    recs.sort(key=lambda r: (severity_order.get(r["severity"], 9), r["component"]))
    return recs


# ===================================================================
# Markdown report
# ===================================================================

def _format_markdown(session_path, messages, hook_results, stop_stats,
                     enforcement, skill_usage, overlaps, recommendations,
                     rule_loader, skill_mcp, verbose):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    L = []
    L.append("# Super-Manager Effectiveness Report")
    L.append(f"\nGenerated: {now}")
    if session_path:
        L.append(f"Session: `{os.path.basename(session_path)}` ({len(messages)} messages)")
    L.append("")

    # -- Pipeline Summary --
    L.append("## Pipeline Summary")
    L.append("")
    L.append("| Stage | Component | Events | Key Metric |")
    L.append("| --- | --- | ---: | --- |")
    L.append(f"| UserPromptSubmit | Rule Loader | {rule_loader.get('total_triggers', 0)} | "
             f"{len(rule_loader.get('per_rule', {}))} rules triggered |")
    L.append(f"| UserPromptSubmit | Skill Matcher | {skill_mcp.get('total_prompts', 0)} | "
             f"avg {skill_mcp.get('avg_skills_per_prompt', 0):.1f} skills/prompt |")
    L.append(f"| UserPromptSubmit | MCP Matcher | {skill_mcp.get('mcp_matches', 0)} | "
             f"{len(skill_mcp.get('per_mcp_matched', {}))} MCPs suggested |")
    L.append(f"| PreToolUse | Enforcement Gate | {enforcement.get('total', 0)} | "
             f"{enforcement.get('blocked', 0)} blocked, {enforcement.get('soft_warned', 0)} soft-warned |")
    L.append(f"| PostToolUse | Skill Tracker | {skill_usage.get('total', 0)} | "
             f"{len(skill_usage.get('by_skill', {}))} unique skills |")
    L.append(f"| Stop | Rule Patterns | {stop_stats['total_events']} | "
             f"{stop_stats['blocks']} blocks, {len(stop_stats.get('storms', []))} storms |")
    L.append("")

    # -- Rule Loader Detail --
    L.append("## UserPromptSubmit: Rule Loader")
    L.append("")
    if rule_loader.get("error"):
        L.append(f"_{rule_loader['error']}_")
    else:
        L.append(f"Total triggers: {rule_loader['total_triggers']} "
                 f"(loaded: {rule_loader['loaded']}, cached: {rule_loader['cached']})")
        L.append("")
        L.append("| Rule | Loaded | Cached | Total | Top Keyword |")
        L.append("| --- | ---: | ---: | ---: | --- |")
        items = sorted(rule_loader.get("per_rule", {}).items(),
                       key=lambda x: -(x[1]["loaded"] + x[1]["cached"]))
        for rule_id, data in items[:25]:
            total = data["loaded"] + data["cached"]
            top_kw = max(data["keywords_hit"].items(), key=lambda x: x[1], default=("", 0))
            L.append(f"| {rule_id} | {data['loaded']} | {data['cached']} | "
                     f"{total} | `{top_kw[0]}` ({top_kw[1]}x) |")
    L.append("")

    # -- Skill Matcher Detail --
    L.append("## UserPromptSubmit: Skill Matcher")
    L.append("")
    if skill_mcp.get("error"):
        L.append(f"_{skill_mcp['error']}_")
    else:
        L.append(f"Prompts processed: {skill_mcp['total_prompts']} "
                 f"(matched: {skill_mcp['skill_matches']}, no match: {skill_mcp['no_skill_match']})")
        L.append(f"Avg skills per prompt: {skill_mcp.get('avg_skills_per_prompt', 0):.1f}")
        L.append("")
        if skill_mcp["per_skill_matched"]:
            L.append("| Skill | Times Matched |")
            L.append("| --- | ---: |")
            for name, count in sorted(skill_mcp["per_skill_matched"].items(), key=lambda x: -x[1])[:20]:
                L.append(f"| {name} | {count} |")
        L.append("")
        if skill_mcp["per_mcp_matched"]:
            L.append("### MCP Suggestions")
            L.append("")
            L.append("| MCP | Times Suggested |")
            L.append("| --- | ---: |")
            for name, count in sorted(skill_mcp["per_mcp_matched"].items(), key=lambda x: -x[1]):
                L.append(f"| {name} | {count} |")
    L.append("")

    # -- Enforcement --
    L.append("## PreToolUse: Enforcement Gate")
    L.append("")
    if enforcement.get("error"):
        L.append(f"_{enforcement['error']}_")
    else:
        L.append(f"Total: {enforcement['total']} (blocked: {enforcement['blocked']}, "
                 f"soft-warned: {enforcement['soft_warned']}, fulfilled: {enforcement['fulfilled']})")
        L.append("")
        if enforcement.get("per_tool_blocked"):
            L.append("### Warnings by Tool")
            L.append("")
            L.append("| Tool | Warnings |")
            L.append("| --- | ---: |")
            for tool, count in sorted(enforcement["per_tool_blocked"].items(), key=lambda x: -x[1])[:10]:
                L.append(f"| {tool} | {count} |")
            L.append("")
        if enforcement["per_skill"]:
            L.append("### Skill Suggestion Fulfillment")
            L.append("")
            L.append("| Skill | Suggested | Fulfilled | Rate |")
            L.append("| --- | ---: | ---: | ---: |")
            items = sorted(enforcement["per_skill"].items(), key=lambda x: -x[1]["suggested"])
            limit = 30 if verbose else 15
            for skill, data in items[:limit]:
                sug, ful = data["suggested"], data["fulfilled"]
                rate = f"{ful/sug*100:.0f}%" if sug > 0 else "-"
                L.append(f"| {skill} | {sug} | {ful} | {rate} |")
    L.append("")

    # -- Skill Usage --
    L.append("## PostToolUse: Skill Usage")
    L.append("")
    if skill_usage.get("error"):
        L.append(f"_{skill_usage['error']}_")
    else:
        L.append(f"Total invocations: {skill_usage['total']}")
        L.append("")
        if skill_usage["by_skill"]:
            L.append("| Skill | Uses | Via |")
            L.append("| --- | ---: | --- |")
            for skill, data in sorted(skill_usage["by_skill"].items(), key=lambda x: -x[1]["count"])[:20]:
                L.append(f"| {skill} | {data['count']} | {', '.join(sorted(data['via']))} |")
    L.append("")

    # -- Stop Hooks --
    L.append("## Stop: Rule Patterns")
    L.append("")
    L.append("| Hook | Fires (session) | Rate | Log Fires | Storms | Status |")
    L.append("| --- | ---: | ---: | ---: | ---: | --- |")
    for hid in sorted(hook_results.keys()):
        r = hook_results[hid]
        log_fires = stop_stats["per_hook"].get(hid, 0)
        storm_count = sum(1 for s in stop_stats.get("storms", []) if s["hook"] == hid)
        status = "BROAD" if r["fire_rate"] > 20 else ("STORMY" if storm_count else "OK")
        L.append(f"| {hid} | {r['fires']} | {r['fire_rate']:.1f}% | {log_fires} | {storm_count} | {status} |")
    L.append("")

    if overlaps:
        L.append("### Pattern Overlaps")
        L.append("")
        L.append("| Msg # | Hooks | Preview |")
        L.append("| ---: | --- | --- |")
        for ov in overlaps[:15]:
            L.append(f"| {ov['index']} | {', '.join(ov['hooks'])} | {ov['preview'][:50]} |")
    L.append("")

    # -- Recommendations --
    L.append("## Recommendations")
    L.append("")
    if not recommendations:
        L.append("No issues detected.")
    else:
        for i, rec in enumerate(recommendations, 1):
            L.append(f"{i}. **[{rec['severity']}]** [{rec['component']}] "
                     f"`{rec['hook']}` -- {rec['issue']}")
            L.append(f"   - {rec['action']}")
    L.append("")
    return "\n".join(L)


# ===================================================================
# HTML Dashboard
# ===================================================================

def _format_html(session_path, messages, hook_results, stop_stats,
                 enforcement, skill_usage, overlaps, recommendations,
                 rule_loader, skill_mcp, narrative=None):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    session_name = os.path.basename(session_path) if session_path else "N/A"

    # -- Helpers --
    HOME = os.environ.get("HOME") or os.environ.get("USERPROFILE", "")
    NPP = "C:/Program Files/Notepad++/notepad++.exe"

    def badge(sev):
        colors = {"HIGH": "#f85149", "WARN": "#d29922", "INFO": "#8b949e"}
        return f'<span class="badge-{sev.lower()}">[{sev}]</span>'

    def flink(filepath, label=None):
        """Generate a clickable link that opens a file in Notepad++."""
        if not label:
            label = os.path.basename(filepath)
        # Normalize to forward slashes for JS
        fp = filepath.replace("\\", "/")
        return f'<a href="#" class="flink" data-path="{fp}" title="Open in Notepad++">{label}</a>'

    def rule_link(rule_id):
        """Link to a rule .md file."""
        # Check Stop rules first, then UserPromptSubmit
        for subdir in ["Stop", "UserPromptSubmit"]:
            fpath = os.path.join(RULES_BASE, subdir, f"{rule_id}.md")
            if os.path.isfile(fpath):
                return flink(fpath, f'<code>{rule_id}</code>')
        return f'<code>{rule_id}</code>'

    def hook_link(hook_name):
        """Link to a hook .js file."""
        fpath = os.path.join(HOOKS_DIR, f"{hook_name}")
        if os.path.isfile(fpath):
            return flink(fpath, f'<code>{hook_name}</code>')
        return f'<code>{hook_name}</code>'

    # -- Prepare data rows --

    # Top 10 rules by total triggers
    rule_rows = ""
    for rule_id, data in sorted(rule_loader.get("per_rule", {}).items(),
                                 key=lambda x: -(x[1]["loaded"] + x[1]["cached"]))[:10]:
        total = data["loaded"] + data["cached"]
        top_kw = max(data["keywords_hit"].items(), key=lambda x: x[1], default=("", 0))
        bar_pct = min(total / max(rule_loader.get("total_triggers", 1), 1) * 100 * 5, 100)
        color = "#f85149" if total > 500 else ("#d29922" if total > 200 else "#539bf5")
        rule_rows += f'''<tr><td>{rule_link(rule_id)}</td><td style="color:{color}">{total:,}</td>
          <td><div class="bar"><div class="bar-fill" style="width:{bar_pct:.0f}%;background:{color}"></div></div></td>
          <td><code>{top_kw[0]}</code> ({top_kw[1]:,}x)</td></tr>\n'''

    # Top 10 skills matched
    skill_rows = ""
    top_skill_count = max((c for c in skill_mcp.get("per_skill_matched", {}).values()), default=1)
    for name, count in sorted(skill_mcp.get("per_skill_matched", {}).items(), key=lambda x: -x[1])[:10]:
        bar_pct = count / max(top_skill_count, 1) * 100
        total_prompts = max(skill_mcp.get("total_prompts", 1), 1)
        match_rate = count / total_prompts * 100
        rate_color = "#f85149" if match_rate > 80 else ("#d29922" if match_rate > 50 else "#c9d1d9")
        skill_rows += f'''<tr><td>{name}</td><td>{count:,}</td><td style="color:{rate_color}">{match_rate:.0f}%</td>
          <td><div class="bar"><div class="bar-fill" style="width:{bar_pct:.0f}%;background:#539bf5"></div></div></td></tr>\n'''

    # MCP suggestions (compact)
    mcp_rows = ""
    for name, count in sorted(skill_mcp.get("per_mcp_matched", {}).items(), key=lambda x: -x[1])[:8]:
        mcp_rows += f"<tr><td>{name}</td><td>{count:,}</td></tr>\n"

    # Stop hooks with descriptions
    stop_descs = {
        "no-reconfirm": "Catches Claude restating user instructions as questions instead of acting.",
        "fix-without-asking": "Catches Claude asking permission to fix problems it already found.",
        "no-guessing": "Catches uncertain language -- forces Claude to test instead of speculate.",
        "test-before-done": "Catches Claude wrapping up without verifying changes actually work.",
        "test-yourself": "Catches Claude telling the user to do something instead of doing it.",
        "check-pending-tasks": "Catches Claude saying 'done' when unfinished tasks remain.",
    }
    stop_rows = ""
    for hid in sorted(hook_results.keys()):
        r = hook_results[hid]
        log_fires = stop_stats["per_hook"].get(hid, 0)
        storm_count = sum(1 for s in stop_stats.get("storms", []) if s["hook"] == hid)
        if storm_count:
            status_color, status_icon = "#d29922", "!!"
        elif log_fires > 0:
            status_color, status_icon = "#3fb950", "OK"
        else:
            status_color, status_icon = "#8b949e", "--"
        desc = stop_descs.get(hid, "")
        stop_rows += f'''<tr>
          <td>{rule_link(hid)}<br><span class="desc">{desc}</span></td>
          <td style="text-align:center">{log_fires}</td>
          <td style="text-align:center">{r["fires"]}</td>
          <td style="text-align:center;color:{status_color}">{status_icon}</td></tr>\n'''

    # Enforcement summary
    enf_blocked = enforcement.get("blocked", 0)
    enf_warned = enforcement.get("soft_warned", 0)
    enf_total = enforcement.get("total", 0)
    enf_fulfilled = enforcement.get("fulfilled", 0)
    fulfill_rate = enf_fulfilled / max(enf_total, 1) * 100

    # Top warned tools
    tool_rows = ""
    for tool, count in sorted(enforcement.get("per_tool_blocked", {}).items(), key=lambda x: -x[1])[:6]:
        pct = count / max(enf_total, 1) * 100
        tool_rows += f'''<tr><td><code>{tool}</code></td><td>{count:,}</td>
          <td><div class="bar"><div class="bar-fill" style="width:{pct:.0f}%;background:#d29922"></div></div></td></tr>\n'''

    # Top unfulfilled skills (NEW detail widget)
    unfulfilled_rows = ""
    skill_usage_names = set(skill_usage.get("by_skill", {}).keys())
    for skill_id, data in sorted(enforcement.get("per_skill", {}).items(),
                                  key=lambda x: -x[1]["suggested"])[:10]:
        sug, ful = data["suggested"], data["fulfilled"]
        rate = f"{ful/sug*100:.0f}%" if sug > 0 else "--"
        actually_used = "yes" if skill_id in skill_usage_names else "no"
        rate_color = "#3fb950" if ful > 0 else "#f85149"
        unfulfilled_rows += f'''<tr><td>{skill_id}</td><td>{sug:,}</td><td style="color:{rate_color}">{ful}</td>
          <td>{rate}</td><td>{actually_used}</td></tr>\n'''

    # Skill usage (top 10)
    usage_rows = ""
    for skill, data in sorted(skill_usage.get("by_skill", {}).items(), key=lambda x: -x[1]["count"])[:10]:
        via = ", ".join(sorted(data["via"]))
        usage_rows += f"<tr><td>{skill}</td><td>{data['count']}</td><td>{via}</td></tr>\n"

    # Recommendations: narrative (from claude -p) + structured fallback
    high_count = sum(1 for r in recommendations if r["severity"] == "HIGH")
    warn_count = sum(1 for r in recommendations if r["severity"] == "WARN")
    info_count = sum(1 for r in recommendations if r["severity"] == "INFO")

    # Convert narrative markdown to HTML (basic conversion)
    def md_to_html(md_text):
        """Minimal markdown to HTML: bold, paragraphs, numbered lists, headers."""
        import re as _re

        def inline(text):
            """Convert bold and inline code markers."""
            text = _re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
            text = _re.sub(r'`(.+?)`', r'<code>\1</code>', text)
            return text

        lines = md_text.split("\n")
        html_out = []
        in_list = False
        for line in lines:
            stripped = line.strip()
            if not stripped:
                if in_list:
                    html_out.append("</ol>")
                    in_list = False
                html_out.append("")
                continue
            # Headers
            if stripped.startswith("### "):
                if in_list:
                    html_out.append("</ol>")
                    in_list = False
                html_out.append(f'<h3 style="color:#e6edf3;font-size:14px;margin:16px 0 6px">{inline(stripped[4:])}</h3>')
                continue
            if stripped.startswith("## "):
                if in_list:
                    html_out.append("</ol>")
                    in_list = False
                html_out.append(f'<h3 style="color:#58a6ff;font-size:14px;margin:16px 0 6px">{inline(stripped[3:])}</h3>')
                continue
            # Numbered list
            m = _re.match(r'^(\d+)\.\s+(.*)', stripped)
            if m:
                if not in_list:
                    html_out.append('<ol style="margin:6px 0;padding-left:24px">')
                    in_list = True
                html_out.append(f"<li>{inline(m.group(2))}</li>")
                continue
            if in_list:
                html_out.append("</ol>")
                in_list = False
            html_out.append(f"<p style='margin:4px 0'>{inline(stripped)}</p>")
        if in_list:
            html_out.append("</ol>")
        return "\n".join(html_out)

    narrative_html = ""
    if narrative:
        narrative_html = md_to_html(narrative)

    # Structured per-item list (shown as collapsible detail if narrative exists)
    rec_items_html = ""
    if not recommendations:
        rec_items_html = '<div class="rec rec-ok">All clear. No patterns too broad, no storms, no overlaps detected.</div>'
    else:
        for rec in recommendations:
            section = rec.get("section", "")
            anchor = f' <a href="#{section}" class="rec-jump">jump to section</a>' if section else ""
            rec_items_html += f'''<div class="rec rec-{rec["severity"].lower()}">{badge(rec["severity"])}
              <code>{rec["hook"]}</code> &mdash; {rec["issue"]}{anchor}<br>
              <span class="action">{rec["action"]}</span></div>\n'''

    # Pipeline flow
    pipeline_steps = [
        ("1", "#3fb950", "UserPromptSubmit", "tool-reminder.js",
         "Scans your prompt against rule keywords and skill registries. "
         "Injects matched rules, suggests skills and MCP servers.",
         f'<a href="#rules">{rule_loader.get("total_triggers", 0):,} rule triggers</a>, '
         f'<a href="#skills">{skill_mcp.get("skill_matches", 0):,} skill matches</a>'),
        ("2", "#539bf5", "PreToolUse", "enforcement-gate.js",
         "Before every tool call (Bash, Read, Write...), checks if a specialized "
         "skill was suggested but not yet used. Logs soft warnings.",
         f'<a href="#enforcement">{enf_total:,} checks</a>, {enf_blocked:,} blocked, {enf_warned:,} warned'),
        ("3", "#8957e5", "PostToolUse", "check-enforcement.js",
         "After Skill/Task tool calls, marks suggestions as fulfilled. "
         "Logs skill usage for analytics.",
         f'<a href="#usage">{skill_usage.get("total", 0)} skill invocations</a>, {enf_fulfilled:,} fulfilled'),
        ("4", "#e5534b", "Stop", "rule-stop.js",
         "Before Claude finishes responding, tests its output against 6 behavioral "
         "patterns. Blocks responses that ask instead of act.",
         f'<a href="#stop">{stop_stats["blocks"]} blocks</a> across {len(hook_results)} rules'),
    ]

    flow_html = ""
    for step_num, color, event, hook, desc, stat in pipeline_steps:
        hl = hook_link(hook)
        flow_html += f'''
        <div class="flow-step" style="border-left:3px solid {color}">
          <div class="flow-header">
            <span class="flow-num" style="background:{color}">{step_num}</span>
            <span class="flow-event">{event}</span>
            <span class="flow-hook">{hl}</span>
          </div>
          <div class="flow-desc">{desc}</div>
          <div class="flow-stat">{stat}</div>
        </div>'''

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Super-Manager Dashboard</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#0d1117; color:#c9d1d9; font-family:'Segoe UI',system-ui,sans-serif;
  padding:32px; max-width:1200px; margin:0 auto; line-height:1.5; }}
h1 {{ color:#e6edf3; font-size:22px; font-weight:600; }}
h2 {{ color:#e6edf3; font-size:16px; font-weight:600; margin:0 0 4px; }}
.subtitle {{ color:#8b949e; font-size:13px; margin-bottom:16px; }}
.meta {{ color:#8b949e; font-size:12px; margin:4px 0 24px; }}
.section {{ margin-bottom:28px; }}
.section-title {{ color:#58a6ff; font-size:13px; font-weight:600; text-transform:uppercase;
  letter-spacing:1px; margin-bottom:12px; padding-bottom:6px; border-bottom:1px solid #21262d; }}
.panel {{ background:#161b22; border:1px solid #30363d; border-radius:8px; padding:16px; margin-bottom:12px; }}
.grid {{ display:grid; gap:12px; }}
.grid-2 {{ grid-template-columns:1fr 1fr; }}
.grid-3 {{ grid-template-columns:1fr 1fr 1fr; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th {{ text-align:left; color:#8b949e; border-bottom:1px solid #21262d; padding:4px 8px; font-weight:500; font-size:11px; text-transform:uppercase; letter-spacing:0.5px; }}
td {{ padding:6px 8px; border-bottom:1px solid #21262d10; vertical-align:top; }}
code {{ background:#21262d; padding:1px 5px; border-radius:3px; font-size:12px; color:#e6edf3; }}
.desc {{ color:#8b949e; font-size:11px; display:block; margin-top:2px; }}
.bar {{ height:4px; border-radius:2px; background:#21262d; width:100px; display:inline-block; vertical-align:middle; }}
.bar-fill {{ height:4px; border-radius:2px; display:block; }}
a {{ color:#58a6ff; text-decoration:none; }}
a:hover {{ text-decoration:underline; }}

/* File links */
.flink {{ color:#58a6ff; cursor:pointer; border-bottom:1px dotted #58a6ff; }}
.flink:hover {{ color:#79c0ff; }}
.flink-toast {{ position:fixed; bottom:20px; right:20px; background:#238636; color:#fff;
  padding:8px 16px; border-radius:6px; font-size:13px; opacity:0; transition:opacity 0.3s;
  pointer-events:none; z-index:9999; }}
.flink-toast.show {{ opacity:1; }}

/* Recommendations */
.rec {{ border:1px solid #30363d; border-radius:6px; padding:10px 14px; margin:6px 0; background:#161b22; font-size:13px; }}
.rec-high {{ border-left:3px solid #f85149; }}
.rec-warn {{ border-left:3px solid #d29922; }}
.rec-info {{ border-left:3px solid #8b949e; }}
.rec-ok {{ border-left:3px solid #238636; color:#3fb950; }}
.badge-high {{ color:#f85149; font-weight:700; }}
.badge-warn {{ color:#d29922; font-weight:700; }}
.badge-info {{ color:#8b949e; font-weight:700; }}
.action {{ color:#8b949e; font-size:12px; display:block; margin-top:4px; }}
.rec-jump {{ font-size:11px; color:#8b949e; margin-left:6px; }}
.rec-jump:hover {{ color:#58a6ff; }}

/* Rec summary bar */
.rec-bar {{ display:flex; gap:12px; align-items:center; margin-bottom:12px; font-size:13px; }}
.rec-bar .pill {{ padding:2px 10px; border-radius:10px; font-weight:600; font-size:12px; }}

/* Pipeline flow */
.flow-step {{ padding:10px 14px; margin-bottom:8px; background:#161b22; border-radius:6px; }}
.flow-header {{ display:flex; align-items:center; gap:8px; margin-bottom:4px; }}
.flow-num {{ display:inline-block; width:20px; height:20px; border-radius:50%; color:#0d1117;
  font-size:11px; font-weight:700; text-align:center; line-height:20px; }}
.flow-event {{ color:#e6edf3; font-weight:600; font-size:14px; }}
.flow-hook {{ color:#8b949e; font-size:12px; }}
.flow-desc {{ color:#8b949e; font-size:12px; margin-left:28px; }}
.flow-stat {{ color:#58a6ff; font-size:12px; font-weight:500; margin-left:28px; margin-top:2px; }}
.flow-stat a {{ color:#58a6ff; }}

/* Stat cards */
.stat {{ text-align:center; padding:14px 8px; cursor:pointer; }}
.stat:hover {{ background:#1c2128; }}
.stat .num {{ font-size:24px; font-weight:700; color:#e6edf3; }}
.stat .label {{ font-size:11px; color:#8b949e; margin-top:2px; }}
</style>
</head>
<body>

<h1>Super-Manager Effectiveness</h1>
<div class="meta">Session: <code>{session_name}</code> ({len(messages)} messages) &middot; {now}</div>

<!-- ============================================================ -->
<!-- ANALYSIS (AT TOP) -->
<!-- ============================================================ -->
<div class="section" id="recommendations">
  <div class="section-title">Analysis</div>
  <div class="rec-bar">
    <span class="pill" style="background:#f8514933;color:#f85149">{high_count} critical</span>
    <span class="pill" style="background:#d2992233;color:#d29922">{warn_count} warnings</span>
    <span class="pill" style="background:#8b949e33;color:#8b949e">{info_count} info</span>
  </div>
  {"<div class='panel' style='font-size:13px;line-height:1.7'>" + narrative_html + "</div>" if narrative_html else ""}
  <details style="margin-top:8px">
    <summary style="cursor:pointer;color:#8b949e;font-size:12px">Individual findings ({len(recommendations)})</summary>
    <div style="margin-top:8px">
    {rec_items_html}
    </div>
  </details>
</div>

<!-- ============================================================ -->
<!-- HOW THE PIPELINE WORKS -->
<!-- ============================================================ -->
<div class="section">
  <div class="section-title">How the Pipeline Works</div>
  <div class="subtitle">Every prompt flows through 4 stages. Each stage has hooks that shape Claude's behavior. Click stats to jump to details.</div>
  {flow_html}
</div>

<!-- ============================================================ -->
<!-- WHAT FIRED THIS SESSION -->
<!-- ============================================================ -->
<div class="section">
  <div class="section-title">Session Summary</div>
  <div class="grid grid-3">
    <a href="#rules" style="text-decoration:none"><div class="panel stat"><div class="num">{rule_loader.get("total_triggers", 0):,}</div><div class="label">Rule Triggers</div></div></a>
    <a href="#enforcement" style="text-decoration:none"><div class="panel stat"><div class="num">{enf_total:,}</div><div class="label">Enforcement Checks</div></div></a>
    <a href="#stop" style="text-decoration:none"><div class="panel stat"><div class="num">{stop_stats["blocks"]}</div><div class="label">Stop Blocks</div></div></a>
  </div>
</div>

<!-- ============================================================ -->
<!-- STAGE 1: RULES -->
<!-- ============================================================ -->
<div class="section" id="rules">
  <div class="section-title">Stage 1: Rule Loader</div>
  <div class="subtitle">
    Matches your prompt keywords against {len(rule_loader.get("per_rule", {}))} rule files in <code>~/.claude/rules/</code>.
    Matched rules inject context so Claude knows project conventions before responding.
    Click any rule name to open the file.
  </div>
  <div class="panel">
    <h2>Top Rules by Trigger Count</h2>
    <table>
    <tr><th>Rule</th><th>Triggers</th><th></th><th>Hottest Keyword</th></tr>
    {rule_rows}
    </table>
  </div>
</div>

<!-- ============================================================ -->
<!-- STAGE 1b: SKILL + MCP MATCHING -->
<!-- ============================================================ -->
<div class="section" id="skills">
  <div class="section-title">Stage 1: Skill + MCP Matching</div>
  <div class="subtitle">
    Same hook also matches skills (by SKILL.md keywords) and MCP servers (by servers.yaml keywords).
    Avg <strong>{skill_mcp.get("avg_skills_per_prompt", 0):.1f}</strong> skills matched per prompt.
    Match rate shows what % of all prompts trigger each skill -- red means it fires on almost everything.
  </div>
  <div class="grid grid-2">
    <div class="panel">
      <h2>Top Skills Matched</h2>
      <table>
      <tr><th>Skill</th><th>Matches</th><th>Rate</th><th></th></tr>
      {skill_rows}
      </table>
    </div>
    <div class="panel">
      <h2>MCP Servers Suggested</h2>
      <table>
      <tr><th>Server</th><th>Times</th></tr>
      {mcp_rows}
      </table>
    </div>
  </div>
</div>

<!-- ============================================================ -->
<!-- STAGE 2: ENFORCEMENT -->
<!-- ============================================================ -->
<div class="section" id="enforcement">
  <div class="section-title">Stage 2: Enforcement Gate</div>
  <div class="subtitle">
    Before every tool call, checks if a specialized skill was suggested but Claude used a generic tool instead.
    Fulfillment rate: <strong style="color:{'#f85149' if fulfill_rate < 5 else '#3fb950'}">{fulfill_rate:.1f}%</strong>
    ({enf_fulfilled:,} fulfilled / {enf_total:,} total).
  </div>
  <div class="grid grid-2">
    <div class="panel">
      <h2>Warnings by Tool</h2>
      <div class="subtitle">Which generic tools triggered enforcement warnings</div>
      <table>
      <tr><th>Tool</th><th>Warnings</th><th></th></tr>
      {tool_rows}
      </table>
    </div>
    <div class="panel">
      <h2>Enforcement Summary</h2>
      <table>
      <tr><td>Hard blocked (auth URLs)</td><td style="color:#f85149">{enf_blocked:,}</td></tr>
      <tr><td>Soft warned (log only)</td><td style="color:#d29922">{enf_warned:,}</td></tr>
      <tr><td>Fulfilled (skill used)</td><td style="color:#3fb950">{enf_fulfilled:,}</td></tr>
      <tr><td>Total checks</td><td>{enf_total:,}</td></tr>
      </table>
    </div>
  </div>
</div>

<!-- ============================================================ -->
<!-- STAGE 2b: UNFULFILLED SKILLS (NEW DETAIL WIDGET) -->
<!-- ============================================================ -->
<div class="section" id="enforcement-detail">
  <div class="section-title">Enforcement Detail: Top Suggested Skills</div>
  <div class="subtitle">
    Which skills were suggested by the enforcement gate and whether Claude actually used them.
    "Invoked" = appeared in skill-usage.jsonl (via Skill or Task tool).
  </div>
  <div class="panel">
    <table>
    <tr><th>Skill</th><th>Times Suggested</th><th>Fulfilled</th><th>Rate</th><th>Invoked?</th></tr>
    {unfulfilled_rows}
    </table>
  </div>
</div>

<!-- ============================================================ -->
<!-- STAGE 3: SKILL USAGE -->
<!-- ============================================================ -->
<div class="section" id="usage">
  <div class="section-title">Stage 3: Skill Usage Tracking</div>
  <div class="subtitle">
    After Skill/Task tool calls, logs which skill was invoked. {skill_usage.get("total", 0)} total invocations across {len(skill_usage.get("by_skill", {}))} unique skills.
  </div>
  <div class="panel">
    <table>
    <tr><th>Skill</th><th>Uses</th><th>Invoked Via</th></tr>
    {usage_rows}
    </table>
  </div>
</div>

<!-- ============================================================ -->
<!-- STAGE 4: STOP HOOKS -->
<!-- ============================================================ -->
<div class="section" id="stop">
  <div class="section-title">Stage 4: Stop Rules (Behavioral Guardrails)</div>
  <div class="subtitle">
    Before Claude finishes responding, {hook_link("rule-stop.js")} tests the response text against
    regex patterns. If a pattern matches, the response is blocked and Claude must try again.
    Click any rule name to open the file.
  </div>
  <div class="panel">
    <table>
    <tr><th>Rule + What It Catches</th><th style="text-align:center">All-Time</th><th style="text-align:center">Session</th><th style="text-align:center">Health</th></tr>
    {stop_rows}
    </table>
  </div>
</div>

<!-- File link handler -->
<div class="flink-toast" id="toast">Path copied -- paste into terminal to open</div>
<script>
document.querySelectorAll('.flink').forEach(function(el) {{
  el.addEventListener('click', function(e) {{
    e.preventDefault();
    var p = this.getAttribute('data-path');
    // Try to copy the notepad++ command to clipboard
    var cmd = '"C:/Program Files/Notepad++/notepad++.exe" "' + p + '"';
    navigator.clipboard.writeText(cmd).then(function() {{
      var toast = document.getElementById('toast');
      toast.textContent = 'Copied: ' + p.split('/').pop();
      toast.classList.add('show');
      setTimeout(function() {{ toast.classList.remove('show'); }}, 2000);
    }}).catch(function() {{
      // Fallback: just show path
      prompt('Open in Notepad++:', cmd);
    }});
  }});
}});
</script>

</body>
</html>"""
    return html


# ===================================================================
# Narrative analysis via claude -p
# ===================================================================

def _build_analysis_summary(messages, rule_loader, skill_mcp, enforcement,
                             skill_usage, stop_stats, hook_results, overlaps):
    """Build compact JSON summary of all analysis data for LLM narrative."""
    total_prompts = skill_mcp.get("total_prompts", 0) or 1

    # Top 10 rules by triggers
    top_rules = []
    for rid, data in sorted(rule_loader.get("per_rule", {}).items(),
                             key=lambda x: -(x[1].get("loaded", 0) + x[1].get("cached", 0)))[:10]:
        triggers = data.get("loaded", 0) + data.get("cached", 0)
        top_kw = ""
        kw_hits = data.get("keywords_hit", {})
        if kw_hits:
            top_kw = max(kw_hits, key=kw_hits.get)
        top_rules.append({"rule": rid, "triggers": triggers,
                          "top_keyword": top_kw, "top_kw_count": kw_hits.get(top_kw, 0)})

    # Keyword overlap (multiple rules sharing same keyword)
    kw_to_rules = defaultdict(list)
    for rid, data in rule_loader.get("per_rule", {}).items():
        for kw in data.get("keywords_hit", {}):
            kw_to_rules[kw].append(rid)
    overlapping_kws = {kw: rules for kw, rules in kw_to_rules.items() if len(rules) >= 3}

    # Top 10 skills by match count
    top_skills = []
    for name, count in sorted(skill_mcp.get("per_skill_matched", {}).items(),
                               key=lambda x: -x[1])[:10]:
        pct = count / total_prompts * 100 if total_prompts else 0
        top_skills.append({"skill": name, "matches": count, "pct_of_prompts": round(pct, 1)})

    # Enforcement summary
    enf = {
        "total": enforcement.get("total", 0),
        "blocked": enforcement.get("blocked", 0),
        "soft_warned": enforcement.get("soft_warned", 0),
        "fulfilled": enforcement.get("fulfilled", 0),
    }
    # Top unfulfilled skills
    skill_usage_names = set(skill_usage.get("by_skill", {}).keys())
    top_unfulfilled = []
    for sid, data in sorted(enforcement.get("per_skill", {}).items(),
                             key=lambda x: -x[1]["suggested"])[:10]:
        top_unfulfilled.append({
            "skill": sid,
            "suggested": data["suggested"],
            "fulfilled": data["fulfilled"],
            "actually_invoked": sid in skill_usage_names,
        })
    enf["top_unfulfilled"] = top_unfulfilled
    enf["fulfillment_rate_pct"] = round(
        enforcement.get("fulfilled", 0) / max(enforcement.get("total", 0), 1) * 100, 2)

    # Skill usage top 10
    top_used = []
    for name, data in sorted(skill_usage.get("by_skill", {}).items(),
                              key=lambda x: -x[1]["count"])[:10]:
        top_used.append({"skill": name, "count": data["count"],
                         "via": list(data.get("via", set()))})

    # Stop hooks
    stop = {"total_blocks": stop_stats.get("blocks", 0),
            "storms": len(stop_stats.get("storms", [])),
            "rules": []}
    for hid, r in hook_results.items():
        log_fires = stop_stats["per_hook"].get(hid, 0)
        stop["rules"].append({"id": hid, "session_fires": r["fires"],
                               "alltime_fires": log_fires,
                               "fire_rate_pct": round(r["fire_rate"], 1)})

    # Overlaps
    overlap_summary = []
    for ov in overlaps[:5]:
        overlap_summary.append({"hooks": ov["hooks"], "text_preview": ov.get("preview", "")[:80]})

    return {
        "session_messages": len(messages),
        "total_prompts": total_prompts,
        "stage1_rules": {
            "total_triggers": rule_loader.get("total_triggers", 0),
            "num_rules": len(rule_loader.get("per_rule", {})),
            "top_rules": top_rules,
            "overlapping_keywords": {kw: rules for kw, rules in
                                      sorted(overlapping_kws.items(),
                                             key=lambda x: -len(x[1]))[:5]},
        },
        "stage1_skills": {
            "avg_per_prompt": skill_mcp.get("avg_skills_per_prompt", 0),
            "top_skills": top_skills,
        },
        "stage2_enforcement": enf,
        "stage3_usage": {"total_invocations": skill_usage.get("total", 0),
                         "unique_skills": len(skill_usage.get("by_skill", {})),
                         "top_used": top_used},
        "stage4_stop": stop,
        "overlaps": overlap_summary,
    }


def _generate_narrative(summary):
    """Generate narrative analysis from structured data (pure Python, no LLM)."""
    parts = []

    # --- Stage 1: Rule Loader ---
    rules = summary["stage1_rules"]
    top = rules["top_rules"]
    overlapping = rules["overlapping_keywords"]

    parts.append("**Stage 1: Rule Loader**")
    if top:
        top1 = top[0]
        parts.append(
            f"`{top1['rule']}` is the most triggered rule at {top1['triggers']:,}x, "
            f"driven by keyword `{top1['top_keyword']}` ({top1['top_kw_count']:,}x). "
        )
        # Check for broad keywords
        broad = [r for r in top if r["top_kw_count"] > 200]
        if broad:
            kws = set(r["top_keyword"] for r in broad)
            parts.append(
                f"Keywords {', '.join('`' + k + '`' for k in sorted(kws))} "
                f"are too broad -- they fire on unrelated prompts. "
            )
    if overlapping:
        for kw, rule_list in list(overlapping.items())[:2]:
            parts.append(
                f"{len(rule_list)} rules share keyword `{kw}` "
                f"({', '.join('`' + r + '`' for r in rule_list[:4])}). "
                f"That's {len(rule_list)} rule files injected for every prompt "
                f"containing \"{kw}\" -- massive context waste."
            )
    parts.append("")

    # --- Stage 1: Skill Matcher ---
    skills = summary["stage1_skills"]
    tp = summary["total_prompts"] or 1
    parts.append("**Stage 1: Skill Matcher**")
    noisy = [s for s in skills["top_skills"] if s["pct_of_prompts"] > 80]
    if noisy:
        names = ", ".join(f"`{s['skill']}` ({s['pct_of_prompts']:.0f}%)" for s in noisy[:4])
        parts.append(
            f"{names} match >80% of prompts. These aren't real matches, "
            f"they're noise. Their keywords are so broad they fire on everything."
        )
    else:
        parts.append(
            f"Skill matching looks healthy -- avg {skills['avg_per_prompt']:.1f} "
            f"skills matched per prompt, no single skill dominates."
        )
    parts.append("")

    # --- Stage 2: Enforcement ---
    enf = summary["stage2_enforcement"]
    parts.append("**Stage 2: Enforcement Gate**")
    rate = enf["fulfillment_rate_pct"]
    parts.append(
        f"{enf['total']:,} enforcement checks: {enf['blocked']:,} hard blocked, "
        f"{enf['soft_warned']:,} soft warned, {enf['fulfilled']} fulfilled. "
        f"Fulfillment rate: **{rate}%**. "
    )
    if rate < 5 and enf["total"] > 100:
        parts.append(
            f"The enforcement system is screaming at Claude {enf['soft_warned']:,} times "
            f"but Claude only uses the suggested skill {enf['fulfilled']} times. "
            f"Either the suggestions are wrong or Claude ignores them."
        )
    # Top unfulfilled
    never_used = [u for u in enf.get("top_unfulfilled", [])
                  if u["fulfilled"] < 5 and not u["actually_invoked"] and u["suggested"] > 500]
    if never_used:
        names = ", ".join(f"`{u['skill']}` ({u['suggested']:,}x)" for u in never_used[:4])
        parts.append(f"Worst offenders: {names} -- suggested thousands of times, never used.")
    # Disconnect: invoked but not fulfilled
    invoked_not_fulfilled = [u for u in enf.get("top_unfulfilled", [])
                             if u["actually_invoked"] and u["fulfilled"] < 2]
    if invoked_not_fulfilled:
        names = ", ".join(f"`{u['skill']}`" for u in invoked_not_fulfilled[:3])
        parts.append(
            f"Interesting: {names} ARE invoked (visible in skill usage logs) "
            f"but the enforcement gate doesn't mark them fulfilled. "
            f"The tracking is disconnected."
        )
    parts.append("")

    # --- Stage 3: Skill Usage ---
    usage = summary["stage3_usage"]
    parts.append("**Stage 3: Skill Usage**")
    parts.append(
        f"{usage['total_invocations']} total invocations across "
        f"{usage['unique_skills']} unique skills. "
    )
    if usage["top_used"]:
        top_names = ", ".join(f"`{u['skill']}` ({u['count']})" for u in usage["top_used"][:5])
        parts.append(f"Most used: {top_names}.")
    agents = [u for u in usage["top_used"] if "Task" in u.get("via", [])]
    if agents:
        agent_count = sum(a["count"] for a in agents)
        parts.append(
            f"Note: {agent_count} of those are Task agents (Explore, general-purpose) "
            f"-- not skills the user explicitly invoked."
        )
    parts.append("")

    # --- Stage 4: Stop Rules ---
    stop = summary["stage4_stop"]
    parts.append("**Stage 4: Stop Rules**")
    parts.append(
        f"{stop['total_blocks']} total blocks across {len(stop['rules'])} rules. "
    )
    if stop["storms"]:
        parts.append(f"{stop['storms']} blocking storms detected.")
    active = [r for r in stop["rules"] if r["session_fires"] > 0]
    dormant = [r for r in stop["rules"] if r["alltime_fires"] > 20 and r["session_fires"] == 0]
    never = [r for r in stop["rules"] if r["alltime_fires"] == 0 and r["session_fires"] == 0]
    if active:
        names = ", ".join(f"`{r['id']}` ({r['session_fires']})" for r in active)
        parts.append(f"Active this session: {names}.")
    if dormant:
        names = ", ".join(f"`{r['id']}` ({r['alltime_fires']} all-time)" for r in dormant)
        parts.append(
            f"Dormant but historically active: {names}. "
            f"These may have already trained Claude's behavior -- good sign."
        )
    if never:
        names = ", ".join(f"`{r['id']}`" for r in never)
        parts.append(f"Never fired: {names}. Test with a deliberate prompt to verify patterns work.")
    parts.append("")

    # --- Priority Actions ---
    actions = []
    if overlapping:
        top_kw = list(overlapping.keys())[0]
        actions.append(
            f"**Deduplicate `{top_kw}` keyword** -- {len(overlapping[top_kw])} rules "
            f"inject overlapping context. Merge or remove `{top_kw}` from most rules."
        )
    if noisy:
        actions.append(
            f"**Narrow skill keywords** for {', '.join('`' + s['skill'] + '`' for s in noisy[:3])} "
            f"-- matching >80% of prompts means the keywords are meaningless."
        )
    if rate < 5 and enf["total"] > 100:
        actions.append(
            f"**Fix enforcement tracking** -- {rate}% fulfillment rate means "
            f"the suggestion system isn't working. Either narrow suggestions or "
            f"fix the fulfillment detection."
        )
    if never_used:
        actions.append(
            f"**Remove dead suggestions** -- skills like "
            f"{', '.join('`' + u['skill'] + '`' for u in never_used[:2])} "
            f"are suggested thousands of times but never used."
        )
    if invoked_not_fulfilled:
        actions.append(
            f"**Fix fulfillment tracking** -- skills like "
            f"{', '.join('`' + u['skill'] + '`' for u in invoked_not_fulfilled[:2])} "
            f"are used but enforcement doesn't detect it."
        )

    if actions:
        parts.append("### Priority Actions")
        for i, action in enumerate(actions[:5], 1):
            parts.append(f"{i}. {action}")

    return "\n".join(parts)


# ===================================================================
# Main entry point
# ===================================================================

def run(session_path=None, verbose=False, diagram=False, html=True):
    ensure_directory(REPORTS_DIR)

    if not session_path:
        session_path = _find_latest_session()
    messages = extract_assistant_messages(session_path)
    hooks = load_stop_hooks()

    # Run all analysis modules
    hook_results = analyze_stop_hooks(hooks, messages)
    stop_stats = analyze_stop_log()
    rule_loader = analyze_rule_loader()
    skill_mcp = analyze_skill_mcp_matcher()
    enforcement = analyze_enforcement()
    skill_usage = analyze_skill_usage()
    overlaps = detect_overlap(hooks, messages)
    recommendations = generate_recommendations(
        hook_results, stop_stats, overlaps, messages, rule_loader, skill_mcp,
        enforcement, skill_usage)

    # Generate narrative analysis via claude -p
    summary = _build_analysis_summary(messages, rule_loader, skill_mcp, enforcement,
                                       skill_usage, stop_stats, hook_results, overlaps)
    narrative = _generate_narrative(summary)

    # Write markdown report
    md = _format_markdown(session_path, messages, hook_results, stop_stats,
                          enforcement, skill_usage, overlaps, recommendations,
                          rule_loader, skill_mcp, verbose)
    atomic_write(ANALYSIS_REPORT, md)

    # Write HTML dashboard
    if html:
        html_content = _format_html(session_path, messages, hook_results, stop_stats,
                                     enforcement, skill_usage, overlaps, recommendations,
                                     rule_loader, skill_mcp, narrative=narrative)
        atomic_write(HTML_REPORT, html_content)

    log.info(f"Report: {len(messages)} msgs, {stop_stats['blocks']} blocks, "
             f"{rule_loader.get('total_triggers', 0)} rule triggers, "
             f"{len(recommendations)} recommendations")

    # Stdout summary
    print(f"Effectiveness Report -> {ANALYSIS_REPORT}")
    if html:
        print(f"HTML Dashboard     -> {HTML_REPORT}")
    print()
    print(f"Session: {len(messages)} messages")
    print(f"Rules: {rule_loader.get('total_triggers', 0)} triggers across {len(rule_loader.get('per_rule', {}))} rules")
    print(f"Skills: avg {skill_mcp.get('avg_skills_per_prompt', 0):.1f} matched/prompt")
    print(f"Enforcement: {enforcement.get('total', 0)} events ({enforcement.get('blocked', 0)} blocked)")
    print(f"Stop: {stop_stats['blocks']} blocks, {len(stop_stats.get('storms', []))} storms")
    if recommendations:
        high = sum(1 for r in recommendations if r["severity"] == "HIGH")
        warn = sum(1 for r in recommendations if r["severity"] == "WARN")
        print(f"Recommendations: {high} high, {warn} warnings")

    if diagram:
        d2_path = os.path.join(REPORTS_DIR, "hook-lifecycle.d2")
        png_path = os.path.join(REPORTS_DIR, "hook-lifecycle.png")
        if os.path.isfile(d2_path):
            d2_bin = r"C:\Program Files\D2\d2.exe"
            if os.path.isfile(d2_bin):
                import subprocess
                subprocess.run([d2_bin, "--theme", "200", d2_path, png_path], capture_output=True)
                print(f"Diagram: {png_path}")

    has_high = any(r["severity"] == "HIGH" for r in recommendations)
    return 2 if has_high else 0


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Analyze super-manager effectiveness")
    parser.add_argument("--session", help="Path to specific JSONL session file")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--diagram", action="store_true")
    parser.add_argument("--no-html", action="store_true", help="Skip HTML generation")
    parser.add_argument("--open", action="store_true", help="Open HTML report after generation")
    args = parser.parse_args()
    code = run(session_path=args.session, verbose=args.verbose,
               diagram=args.diagram, html=not args.no_html)
    if args.open:
        import subprocess
        subprocess.Popen(["start", "", HTML_REPORT], shell=True)
    sys.exit(code)
