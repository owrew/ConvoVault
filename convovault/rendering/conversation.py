"""
conversation.py
===============
Formats a ConversationTranscript into a publication-grade, complete-archive
Obsidian Markdown document. Every user message, assistant response, thinking
block, tool call, and tool output is preserved in full.
"""
from __future__ import annotations
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from ..models import ConversationTranscript, ConversationMeta, Step, Turn, ToolCall
from ..config.exporter import ExporterConfig
from ..utils.content import (
    clean_user_content, get_date_range,
    TOOL_RESULT_TYPES, TYPE_USER_INPUT, TYPE_PLANNER_RESPONSE,
)
from ..analysis.wikilinks import extract_topics, title_to_filename
from .mermaid import generate_mermaid_diagram


# ── Time helpers ─────────────────────────────────────────────────────────────

def _iso_to_date(iso: str) -> str:
    return iso[:10] if iso else ""

def _unix_to_iso(ts: Optional[int]) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    except Exception:
        return ""

def _unix_to_date(ts: Optional[int]) -> str:
    return _unix_to_iso(ts)[:10] if ts else ""

def _iso_to_display(iso: str) -> str:
    """Convert ISO timestamp to readable display: '2026-06-25 20:06 UTC'"""
    if not iso or len(iso) < 16:
        return iso or ""
    try:
        return iso[:16].replace('T', ' ') + " UTC"
    except Exception:
        return iso

def _duration_str(start_iso: str, end_iso: str) -> str:
    """Human-readable duration between two ISO timestamps."""
    if not start_iso or not end_iso:
        return "unknown"
    try:
        fmt = '%Y-%m-%dT%H:%M:%SZ'
        s = datetime.strptime(start_iso[:19] + 'Z', fmt)
        e = datetime.strptime(end_iso[:19] + 'Z', fmt)
        secs = int((e - s).total_seconds())
        if secs < 60:
            return f"{secs}s"
        if secs < 3600:
            return f"{secs // 60}m {secs % 60}s"
        h = secs // 3600
        m = (secs % 3600) // 60
        return f"{h}h {m}m"
    except Exception:
        return "unknown"


# ── Markdown helpers ──────────────────────────────────────────────────────────

def _safe_code_block(content: str, language: str = "") -> str:
    """Use an adaptive fence length so inner backtick runs cannot break the block."""
    max_backticks = 0
    for match in re.finditer(r'`+', content):
        max_backticks = max(max_backticks, len(match.group(0)))
    fence = '`' * max(max_backticks + 1, 3)
    return f"{fence}{language}\n{content}\n{fence}"

def _clean_planner_content(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ── Tool-call argument extraction helpers ─────────────────────────────────────

_SKIP_ARG_KEYS = {'toolSummary', 'toolAction'}

def _tool_result_title(step: Step) -> str:
    """Build a descriptive title for a tool result block from the step content."""
    content = step.content or ""
    # Try to pull the file path from VIEW_FILE results
    m = re.search(r'File Path:\s*`?([^`\n]+)`?', content)
    if m:
        path = m.group(1).strip()
        # Shorten to last 2 path components
        parts = re.split(r'[/\\]', path.replace('%20', ' '))
        parts = [p for p in parts if p]
        short = '/'.join(parts[-2:]) if len(parts) >= 2 else path
        return f"{step.step_type} → `{short}`"
    # RUN_COMMAND: show first line of content
    if step.step_type == "RUN_COMMAND":
        first = content.strip().split('\n')[0][:80] if content.strip() else ""
        if first:
            return f"RUN_COMMAND → `{first}`"
    return step.step_type


def _format_tool_call(tool_call: ToolCall, max_len: Optional[int] = None) -> str:
    """Format a single tool call as a blockquote with all arguments."""
    name = tool_call.name
    summary = tool_call.tool_summary or tool_call.tool_action or ""
    args = tool_call.args or {}

    arg_lines = []
    for k, v in args.items():
        if k in _SKIP_ARG_KEYS:
            continue
        val_str = str(v)
        if max_len is not None and max_len > 0 and len(val_str) > max_len:
            val_str = val_str[:max_len] + '…'
        # Multiline values go into a nested code block
        if '\n' in val_str and len(val_str) > 80:
            arg_lines.append(f"  - **{k}:**\n    ```\n    {val_str[:2000]}\n    ```")
        else:
            arg_lines.append(f"  - **{k}:** `{val_str}`")

    header = f"🔧 **`{name}`**"
    if summary:
        header += f" — *{summary}*"

    parts = [f"> {header}"]
    if arg_lines:
        parts.extend(f"> {line}" for line in arg_lines)

    return '\n'.join(parts)


# ── Step formatter ────────────────────────────────────────────────────────────

def _format_step(
    step: Step,
    config_no_tool_results: bool,
    max_results: Optional[int],
    result_counter: List[int],
    max_tool_output_length: Optional[int] = None,
) -> str:
    parts: List[str] = []

    if step.step_type == TYPE_USER_INPUT:
        content = clean_user_content(step.content)
        if content:
            parts.append(content)

    elif step.step_type == TYPE_PLANNER_RESPONSE:
        # ── Thinking block (collapsible) ──────────────────────────────────
        if step.thinking:
            parts.append(
                f"<details>\n"
                f"<summary>💭 Thinking Process</summary>\n\n"
                f"{step.thinking.strip()}\n"
                f"</details>"
            )

        # ── Main assistant content ────────────────────────────────────────
        content = _clean_planner_content(step.content)
        if content:
            parts.append(content)

        # ── Tool calls ────────────────────────────────────────────────────
        if step.tool_calls:
            tc_blocks = [
                _format_tool_call(tc, max_tool_output_length)
                for tc in step.tool_calls
            ]
            parts.append('\n'.join(tc_blocks))

    elif step.step_type in TOOL_RESULT_TYPES:
        if not config_no_tool_results:
            is_unlimited = (max_results is None or max_results <= 0)
            if is_unlimited or result_counter[0] < max_results:
                result_counter[0] += 1
                content = step.content or ""
                if content:
                    # Apply optional length cap
                    if max_tool_output_length and max_tool_output_length > 0:
                        truncated = len(content) > max_tool_output_length
                        display = content[:max_tool_output_length]
                        if truncated:
                            display += f'\n\n*[output truncated at {max_tool_output_length:,} chars — use --max-tool-output-length to adjust]*'
                    else:
                        display = content

                    title = _tool_result_title(step)
                    code_block = _safe_code_block(display)
                    ts_label = f" *(step {step.index})*" if step.index else ""
                    parts.append(
                        f"<details>\n"
                        f"<summary>📄 {title}{ts_label}</summary>\n\n"
                        f"{code_block}\n"
                        f"</details>"
                    )
            elif not is_unlimited and result_counter[0] == max_results:
                result_counter[0] += 1
                parts.append(
                    f"> ⚠️ *{max_results} tool results shown — remaining results omitted.*  \n"
                    f"> *Use `--max-tool-results-per-turn` to change this limit.*"
                )

    elif step.step_type in ('UNKNOWN_', 'ERROR') or step.step_type.startswith('UNKNOWN_'):
        content = step.content or ""
        if content:
            parts.append(
                f"<details>\n"
                f"<summary>⚠️ {step.step_type} (step {step.index})</summary>\n\n"
                f"{_safe_code_block(content)}\n"
                f"</details>"
            )

    return '\n\n'.join(p for p in parts if p)


# ── Turn grouper ──────────────────────────────────────────────────────────────

def _group_turns(steps: List[Step]) -> List[Turn]:
    turns: List[Turn] = []
    current_turn: Optional[Turn] = None
    turn_num = 0

    for step in steps:
        if step.step_type == TYPE_USER_INPUT:
            if current_turn:
                turns.append(current_turn)
            turn_num += 1
            current_turn = Turn(
                num=turn_num, source="User",
                timestamp=step.created_at, steps=[step],
            )
        elif step.step_type == TYPE_PLANNER_RESPONSE:
            if current_turn and current_turn.source == "User":
                turns.append(current_turn)
                turn_num += 1
                current_turn = Turn(
                    num=turn_num, source="Assistant",
                    timestamp=step.created_at, steps=[step],
                )
            elif current_turn and current_turn.source == "Assistant":
                current_turn.steps.append(step)
            else:
                if current_turn:
                    turns.append(current_turn)
                turn_num += 1
                current_turn = Turn(
                    num=turn_num, source="Assistant",
                    timestamp=step.created_at, steps=[step],
                )
        else:
            if current_turn:
                current_turn.steps.append(step)

    if current_turn:
        turns.append(current_turn)
    return turns


# ── Statistics collector ──────────────────────────────────────────────────────

def _collect_stats(steps: List[Step]) -> dict:
    user_turns = sum(1 for s in steps if s.step_type == TYPE_USER_INPUT)
    asst_turns = sum(1 for s in steps if s.step_type == TYPE_PLANNER_RESPONSE)
    thinking_blocks = sum(1 for s in steps if s.thinking)
    tool_calls = sum(len(s.tool_calls) for s in steps)
    tool_results = sum(1 for s in steps if s.step_type in TOOL_RESULT_TYPES)
    errors = sum(1 for s in steps if s.step_type == 'ERROR')
    # Unique tool names
    names: Dict[str, int] = {}
    for s in steps:
        for tc in s.tool_calls:
            names[tc.name] = names.get(tc.name, 0) + 1
    return {
        'user_turns': user_turns,
        'asst_turns': asst_turns,
        'thinking_blocks': thinking_blocks,
        'tool_calls': tool_calls,
        'tool_results': tool_results,
        'errors': errors,
        'tool_breakdown': names,
    }


# ── Main formatter ────────────────────────────────────────────────────────────

def format_conversation(
    transcript: ConversationTranscript,
    meta: Optional[ConversationMeta],
    all_meta: Dict[str, ConversationMeta],
    no_tool_results: bool = False,
    max_tool_results_per_turn: Optional[int] = None,
    max_tool_output_length: Optional[int] = None,
    config: Optional[ExporterConfig] = None,
) -> str:
    if config is not None:
        no_tool_results = config.no_tool_results
        max_tool_results_per_turn = config.max_tool_results_per_turn
        max_tool_output_length = config.max_tool_output_length

    conv_id = transcript.conv_id
    steps = transcript.steps

    # ── 1. Metadata resolution ────────────────────────────────────────────────
    title = meta.title if meta else conv_id[:8]
    first_date_iso, last_date_iso = get_date_range(transcript)
    created_date = _iso_to_date(first_date_iso)
    updated_date = _iso_to_date(last_date_iso)

    if meta:
        if meta.created_at and not created_date:
            created_date = _unix_to_date(meta.created_at)
        if meta.updated_at and not updated_date:
            updated_date = _unix_to_date(meta.updated_at)
        last_viewed = _unix_to_date(meta.last_viewed_at) if meta.last_viewed_at else "never"
    else:
        last_viewed = "never"

    duration = _duration_str(first_date_iso or "", last_date_iso or "")
    step_count = len(steps)
    intel = transcript.intelligence
    stats = _collect_stats(steps)

    # ── 2. WikiLinks and tags ─────────────────────────────────────────────────
    all_content = title + " " + " ".join([s.content for s in steps if s.content])
    wiki_links, tags = extract_topics(all_content)

    # ── 3. Frontmatter aliases ────────────────────────────────────────────────
    alias = title.replace('"', "'")
    aliases = [alias]
    if meta and meta.trajectory_id:
        aliases.append(meta.trajectory_id)

    tag_yaml    = '\n'.join(f'  - {t}' for t in tags)
    aliases_yaml = '\n'.join(f'  - "{a}"' for a in aliases)
    tech_yaml   = '\n'.join(f'  - {t}' for t in intel.technologies) if intel.technologies else '  []'
    topics_yaml = '\n'.join(f'  - {t}' for t in intel.topics)       if intel.topics       else '  []'
    langs_yaml  = '\n'.join(f'  - {l}' for l in intel.code_languages) if intel.code_languages else '  []'

    frontmatter = f"""---
id: "{conv_id}"
title: "{alias}"
created: {created_date or 'unknown'}
updated: {updated_date or 'unknown'}
last_viewed: {last_viewed}
duration: "{duration}"
step_count: {step_count}
user_turns: {stats['user_turns']}
assistant_turns: {stats['asst_turns']}
tool_calls_total: {stats['tool_calls']}
thinking_blocks: {stats['thinking_blocks']}
conversation_id: "{conv_id}"
source: "antigravity"
tags:
{tag_yaml}
aliases:
{aliases_yaml}
technologies:
{tech_yaml}
topics:
{topics_yaml}
code_languages:
{langs_yaml}
---"""

    # ── 4. Document body ──────────────────────────────────────────────────────
    body: List[str] = []
    body.append(f"# {title}\n")

    # ── Metadata table ────────────────────────────────────────────────────────
    body.append(
        f"| Field | Value |\n"
        f"| --- | --- |\n"
        f"| **Conversation ID** | `{conv_id}` |\n"
        f"| **Created** | {created_date or 'Unknown'} |\n"
        f"| **Updated** | {updated_date or 'Unknown'} |\n"
        f"| **Last Viewed** | {last_viewed} |\n"
        f"| **Duration** | {duration} |\n"
        f"| **Total Steps** | {step_count} |\n"
        f"| **Source** | Antigravity (Google) |\n"
    )

    # ── Conversation Statistics ───────────────────────────────────────────────
    body.append("## 📊 Conversation Statistics\n")
    body.append(
        f"| Metric | Count |\n"
        f"| --- | --- |\n"
        f"| 👤 User Turns | {stats['user_turns']} |\n"
        f"| 🤖 Assistant Turns | {stats['asst_turns']} |\n"
        f"| 💭 Thinking Blocks | {stats['thinking_blocks']} |\n"
        f"| 🔧 Tool Calls | {stats['tool_calls']} |\n"
        f"| 📄 Tool Results | {stats['tool_results']} |\n"
        f"| ⚠️ Errors | {stats['errors']} |\n"
    )

    # Tool call breakdown
    if stats['tool_breakdown']:
        top = sorted(stats['tool_breakdown'].items(), key=lambda x: -x[1])
        breakdown_rows = '\n'.join(
            f"| `{name}` | {count} |" for name, count in top
        )
        body.append(
            f"### Tool Call Breakdown\n\n"
            f"| Tool | Calls |\n"
            f"| --- | --- |\n"
            f"{breakdown_rows}\n"
        )

    # ── Summary ───────────────────────────────────────────────────────────────
    if intel.summary:
        body.append(f"## 📋 Conversation Summary\n\n{intel.summary}\n")

    # ── Tech graph ────────────────────────────────────────────────────────────
    if intel.technologies:
        diagram = generate_mermaid_diagram(title, intel.technologies)
        if diagram:
            body.append(f"## 📐 Tech Stack Graph\n\n{diagram}\n")

    # ── Technologies ──────────────────────────────────────────────────────────
    if intel.technologies:
        tech_links = "  ".join(f"[[{t}]]" for t in intel.technologies)
        body.append(f"## 🛠️ Technologies\n\n{tech_links}\n")

    # ── Topics ────────────────────────────────────────────────────────────────
    if intel.topics:
        topic_links = "  ".join(f"[[{t}]]" for t in intel.topics)
        body.append(f"## 🏷️ Topics\n\n{topic_links}\n")

    # ── Files Mentioned ───────────────────────────────────────────────────────
    if intel.files_mentioned:
        file_list = '\n'.join(f"- `{f}`" for f in intel.files_mentioned)
        body.append(f"## 📁 Files Mentioned\n\n{file_list}\n")

    # ── Commands Executed ─────────────────────────────────────────────────────
    if intel.commands_executed:
        cmd_list = '\n'.join(f"- `{c}`" for c in intel.commands_executed)
        body.append(f"## ⚡ Commands Executed\n\n{cmd_list}\n")

    # ── Wiki Links ────────────────────────────────────────────────────────────
    if wiki_links:
        wl_str = "  ".join(f"[[{w}]]" for w in wiki_links)
        body.append(f"## 🔗 Wiki Links\n\n{wl_str}\n")

    # ── Related Conversations ─────────────────────────────────────────────────
    if transcript.related_ids:
        related_rows = []
        for r_id in transcript.related_ids:
            r_meta = all_meta.get(r_id)
            if r_meta:
                related_rows.append(f"| [[{r_meta.title}]] | `{r_id}` |")
            else:
                related_rows.append(f"| [[{r_id[:8]}]] | `{r_id}` |")
        body.append(
            f"## 🔄 Related Conversations\n\n"
            f"| Note | Conversation ID |\n"
            f"| --- | --- |\n"
            + '\n'.join(related_rows) + "\n"
        )

    # ── Timeline ──────────────────────────────────────────────────────────────
    timeline_entries: List[str] = []
    for step in steps:
        if step.created_at and step.step_type == TYPE_USER_INPUT:
            content = clean_user_content(step.content)
            first_line = content.split('\n')[0].strip()[:80] if content else ""
            if first_line:
                ts = _iso_to_display(step.created_at)
                timeline_entries.append(f"- **{ts}** — 👤 {first_line}")
        elif step.created_at and step.step_type == TYPE_PLANNER_RESPONSE and step.tool_calls:
            for tc in step.tool_calls:
                summary = tc.tool_summary or tc.tool_action or tc.name
                ts = _iso_to_display(step.created_at)
                timeline_entries.append(f"- **{ts}** — 🔧 `{tc.name}` *{summary}*")
                break  # One entry per step to avoid noise

    if timeline_entries:
        body.append(
            f"## ⏱️ Timeline\n\n"
            + '\n'.join(timeline_entries[:50])
            + ("\n\n*…timeline truncated after 50 entries*" if len(timeline_entries) > 50 else "")
            + "\n"
        )

    # ── Conversation History ──────────────────────────────────────────────────
    body.append("---\n\n## 💬 Conversation History\n")

    turns = _group_turns(steps)
    transcript.turns = turns  # cache in model

    for turn in turns:
        ts = turn.timestamp
        ts_label = f" *(_{_iso_to_display(ts)}_)*" if ts else ""

        if turn.source == "User":
            body.append(f"### 👤 User — Turn {turn.num}{ts_label}\n")
        else:
            body.append(f"### 🤖 Assistant — Turn {turn.num}{ts_label}\n")

        result_counter = [0]
        for step in turn.steps:
            formatted = _format_step(
                step,
                no_tool_results,
                max_tool_results_per_turn,
                result_counter,
                max_tool_output_length,
            )
            if formatted:
                body.append(formatted + "\n")

    # ── Footer ────────────────────────────────────────────────────────────────
    body.append("---")
    body.append("## 🧠 Conversation Intelligence\n")

    if intel.technologies:
        body.append(f"**Technologies:** {', '.join(f'[[{t}]]' for t in intel.technologies)}")
    if intel.topics:
        body.append(f"**Topics:** {', '.join(f'[[{t}]]' for t in intel.topics)}")
    if intel.code_languages:
        body.append(f"**Code Languages:** {', '.join(intel.code_languages)}")
    if intel.files_mentioned:
        # Show ALL files, no truncation
        body.append(f"**Files Mentioned ({len(intel.files_mentioned)}):**\n"
                    + '\n'.join(f"  - `{f}`" for f in intel.files_mentioned))
    if intel.commands_executed:
        # Show ALL commands, no truncation
        body.append(f"**Commands Run ({len(intel.commands_executed)}):**\n"
                    + '\n'.join(f"  - `{c}`" for c in intel.commands_executed))

    if transcript.source_file:
        body.append(f"\n*Source:* `{transcript.source_file}`")
    body.append(f"*Exported by Antigravity Obsidian Exporter v2 · Conversation ID: `{conv_id}`*\n")

    return frontmatter + "\n\n" + "\n".join(body) + "\n"
