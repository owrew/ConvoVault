"""
conversation.py
===============
Formats a ConversationTranscript into a publication-grade Obsidian Markdown document.
"""
from __future__ import annotations
import re
from datetime import datetime, timezone
from typing import List, Dict, Optional
from ..models import ConversationTranscript, ConversationMeta, Step, Turn
from ..config import ExporterConfig
from ..sources.transcript import clean_user_content, get_date_range, TOOL_RESULT_TYPES, TYPE_USER_INPUT, TYPE_PLANNER_RESPONSE
from ..analysis.wikilinks import extract_topics, title_to_filename
from .mermaid import generate_mermaid_diagram

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

def _clean_planner_content(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

def _safe_code_block(content: str, language: str = "") -> str:
    max_backticks = 0
    for match in re.finditer(r'`+', content):
        max_backticks = max(max_backticks, len(match.group(0)))
    fence = '`' * max(max_backticks + 1, 3)
    return f"{fence}{language}\n{content}\n{fence}"

def _format_tool_call(tool_call, max_len: Optional[int] = None) -> str:
    name = tool_call.name
    summary = tool_call.tool_summary or tool_call.tool_action or ""
    args = tool_call.args or {}

    skip_keys = {'toolSummary', 'toolAction'}
    arg_lines = []
    for k, v in args.items():
        if k in skip_keys:
            continue
        val_str = str(v)
        if max_len is not None and max_len > 0 and len(val_str) > max_len:
            val_str = val_str[:max_len] + '…'
        arg_lines.append(f"  - **{k}:** `{val_str}`")

    header = f"🔧 **`{name}`**"
    if summary:
        header += f" — {summary}"

    parts = [f"> {header}"]
    if arg_lines:
        parts.extend(f"> {line}" for line in arg_lines)

    return '\n'.join(parts)

def _format_step(
    step: Step,
    config_no_tool_results: bool,
    max_results: Optional[int],
    result_counter: List[int],
    max_tool_output_length: Optional[int] = None
) -> str:
    parts: List[str] = []

    if step.step_type == TYPE_USER_INPUT:
        content = clean_user_content(step.content)
        if content:
            parts.append(content)

    elif step.step_type == TYPE_PLANNER_RESPONSE:
        # Check thinking process
        if step.thinking:
            parts.append(
                f"<details>\n"
                f"<summary>💭 Thinking Process</summary>\n\n"
                f"{step.thinking.strip()}\n"
                f"</details>"
            )

        content = _clean_planner_content(step.content)
        if content:
            parts.append(content)

        if step.tool_calls:
            tc_blocks = [_format_tool_call(tc, max_tool_output_length) for tc in step.tool_calls]
            parts.append('\n'.join(tc_blocks))

    elif step.step_type in TOOL_RESULT_TYPES:
        if not config_no_tool_results:
            is_unlimited = (max_results is None or max_results <= 0)
            if is_unlimited or result_counter[0] < max_results:
                result_counter[0] += 1
                content = step.content or ""
                if content:
                    if max_tool_output_length is not None and max_tool_output_length > 0:
                        truncated = len(content) > max_tool_output_length
                        display = content[:max_tool_output_length] + (f'\n\n*[output truncated at {max_tool_output_length} chars…]*' if truncated else '')
                    else:
                        display = content
                    code_block = _safe_code_block(display)
                    parts.append(
                        f"<details>\n"
                        f"<summary>📄 Tool result: <code>{step.step_type}</code></summary>\n\n"
                        f"{code_block}\n"
                        f"</details>"
                    )
            elif not is_unlimited and result_counter[0] == max_results:
                result_counter[0] += 1
                parts.append("*[remaining tool results omitted from this turn]*")

    elif step.step_type.startswith('UNKNOWN_') or step.step_type == 'ERROR':
        content = step.content or ""
        if content:
            parts.append(f"> ⚠️ *{step.step_type}*\n>\n> {content}")

    return '\n\n'.join(p for p in parts if p)

def _group_turns(steps: List[Step]) -> List[Turn]:
    turns = []
    current_turn = None
    turn_num = 0

    for step in steps:
        if step.step_type == TYPE_USER_INPUT:
            if current_turn:
                turns.append(current_turn)
            turn_num += 1
            current_turn = Turn(num=turn_num, source="User", timestamp=step.created_at, steps=[step])
        elif step.step_type == TYPE_PLANNER_RESPONSE:
            if current_turn and current_turn.source == "User":
                turns.append(current_turn)
                turn_num += 1
                current_turn = Turn(num=turn_num, source="Assistant", timestamp=step.created_at, steps=[step])
            elif current_turn and current_turn.source == "Assistant":
                current_turn.steps.append(step)
            else:
                if current_turn:
                    turns.append(current_turn)
                turn_num += 1
                current_turn = Turn(num=turn_num, source="Assistant", timestamp=step.created_at, steps=[step])
        else:
            if current_turn:
                current_turn.steps.append(step)
    if current_turn:
        turns.append(current_turn)
    return turns

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

    # 1. Metadata resolution
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

    step_count = len(steps)
    intel = transcript.intelligence
    
    # WikiLinks and tags
    wiki_links, tags = extract_topics(title + " " + " ".join([s.content for s in steps if s.content]))

    # Frontmatter aliases
    alias = title.replace('"', "'")
    aliases = [alias]
    if meta and meta.trajectory_id:
        aliases.append(meta.trajectory_id)

    # 2. Build frontmatter
    tag_yaml = '\n'.join(f'  - {t}' for t in tags)
    aliases_yaml = '\n'.join(f'  - "{a}"' for a in aliases)
    
    frontmatter = f"""---
id: "{conv_id}"
title: "{alias}"
created: {created_date or 'unknown'}
updated: {updated_date or 'unknown'}
last_viewed: {last_viewed}
step_count: {step_count}
conversation_id: "{conv_id}"
tags:
{tag_yaml}
aliases:
{aliases_yaml}
---"""

    # 3. Assemble document
    body = []
    body.append(f"# {title}\n")
    
    # Metadata stats block
    body.append(
        f"| Metadata | Value |\n"
        f"| --- | --- |\n"
        f"| **Created** | {created_date or 'Unknown'} |\n"
        f"| **Updated** | {updated_date or 'Unknown'} |\n"
        f"| **Last Viewed** | {last_viewed} |\n"
        f"| **Steps** | {step_count} |\n"
    )

    # Summary
    if intel.summary:
        body.append(f"## 📋 Summary\n\n{intel.summary}\n")

    # Mermaid diagram (stretch goal)
    if intel.technologies:
        diagram = generate_mermaid_diagram(title, intel.technologies)
        if diagram:
            body.append(f"## 📊 Tech Graph\n\n{diagram}\n")

    # Conversation history turns
    body.append("## 💬 Conversation History\n")
    turns = _group_turns(steps)
    transcript.turns = turns  # cache in model

    for turn in turns:
        ts = turn.timestamp
        ts_label = f" *({ts[:16].replace('T', ' ')})*" if ts else ""
        
        if turn.source == "User":
            body.append(f"### 👤 User — Turn {turn.num}{ts_label}\n")
        else:
            body.append(f"### 🤖 Assistant — Turn {turn.num}{ts_label}\n")

        result_counter = [0]
        for step in turn.steps:
            formatted = _format_step(step, no_tool_results, max_tool_results_per_turn, result_counter, max_tool_output_length)
            if formatted:
                body.append(formatted + "\n")

    # 4. Intelligence Section
    body.append("---")
    body.append("## 🧠 Conversation Intelligence\n")
    
    # Tech / topics / files / commands lists
    if intel.technologies:
        tech_links = ", ".join(f"[[{t}]]" for t in intel.technologies)
        body.append(f"* **Technologies:** {tech_links}")
    if intel.topics:
        topic_links = ", ".join(f"[[{t}]]" for t in intel.topics)
        body.append(f"* **Topics:** {topic_links}")
    if intel.code_languages:
        body.append(f"* **Code Languages:** {', '.join(intel.code_languages)}")
    if intel.files_mentioned:
        body.append(f"* **Files Mentioned:** {', '.join(f'`{f}`' for f in intel.files_mentioned[:15])}")
    if intel.commands_executed:
        cmd_block = "\n".join(f"  - `{c}`" for c in intel.commands_executed[:10])
        body.append(f"* **Commands Run:**\n{cmd_block}")

    # Related conversations
    if transcript.related_ids:
        related_links = []
        for r_id in transcript.related_ids:
            r_meta = all_meta.get(r_id)
            if r_meta:
                related_links.append(f"[[{r_meta.title}]]")
            else:
                related_links.append(f"[[{r_id[:8]}]]")
        body.append(f"* **Related Chats:** {', '.join(related_links)}")

    body.append(f"\n*Exported by Antigravity Exporter v2 · ID: `{conv_id}`*")

    return frontmatter + "\n\n" + "\n".join(body) + "\n"
