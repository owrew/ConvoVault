"""
transcript.py
=============
Parser for Antigravity JSONL transcript files.
"""
from __future__ import annotations
import json
import logging
import os
import re
from typing import Iterator, List, Optional
from ..models import Step, ToolCall, ConversationTranscript

log = logging.getLogger(__name__)

TYPE_USER_INPUT = "USER_INPUT"
TYPE_PLANNER_RESPONSE = "PLANNER_RESPONSE"
TYPE_CONVERSATION_HISTORY = "CONVERSATION_HISTORY"

TOOL_RESULT_TYPES = {
    "VIEW_FILE", "LIST_DIRECTORY", "RUN_COMMAND", "WRITE_FILE",
    "REPLACE_FILE_CONTENT", "MULTI_REPLACE_FILE", "SEARCH_WEB",
    "GREP_SEARCH", "GENERATE_IMAGE", "ASK_QUESTION", "ASK_PERMISSION",
    "BROWSER_SUBAGENT", "INVOKE_SUBAGENT", "SEND_MESSAGE",
    "MANAGE_SUBAGENTS", "MANAGE_TASK", "SCHEDULE",
    "READ_URL_CONTENT", "DEFINE_SUBAGENT",
}

def _jsonl_path(brain_dir: str, conv_id: str) -> Optional[str]:
    base = os.path.join(brain_dir, conv_id, ".system_generated", "logs")
    full = os.path.join(base, "transcript_full.jsonl")
    compact = os.path.join(base, "transcript.jsonl")
    if os.path.isfile(full):
        return full
    if os.path.isfile(compact):
        return compact
    return None

def _parse_tool_calls(raw: Any) -> List[ToolCall]:
    if not raw or not isinstance(raw, list):
        return []
    result = []
    for item in raw:
        if isinstance(item, dict):
            try:
                result.append(ToolCall.from_dict(item))
            except Exception as e:
                log.warning("Malformed tool call object: %s, error: %s", item, e)
    return result

def _iter_steps(jsonl_path: str) -> Iterator[Step]:
    with open(jsonl_path, 'r', encoding='utf-8', errors='replace') as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                log.debug("JSON parse error at line %d in %s: %s", lineno, jsonl_path, e)
                continue

            step_type = obj.get("type", "")
            if step_type == TYPE_CONVERSATION_HISTORY:
                continue

            yield Step(
                index=obj.get("step_index", lineno - 1),
                source=obj.get("source", ""),
                step_type=step_type,
                status=obj.get("status", ""),
                created_at=obj.get("created_at", ""),
                content=obj.get("content", ""),
                thinking=obj.get("thinking", ""),
                tool_calls=_parse_tool_calls(obj.get("tool_calls")),
                truncated=obj.get("is_truncated", False),
            )

def read_transcript(brain_dir: str, conv_id: str) -> Optional[ConversationTranscript]:
    path = _jsonl_path(brain_dir, conv_id)
    if path is None:
        log.debug("No transcript found for %s", conv_id)
        return None

    try:
        steps = list(_iter_steps(path))
        log.debug("Read %d steps from %s", len(steps), path)
        return ConversationTranscript(
            conv_id=conv_id,
            steps=steps,
            source_file=path,
        )
    except Exception as e:
        log.error("Failed to read transcript for %s at %s: %s", conv_id, path, e)
        return None

def get_transcript_mtime(brain_dir: str, conv_id: str) -> Optional[float]:
    path = _jsonl_path(brain_dir, conv_id)
    if path and os.path.isfile(path):
        try:
            return os.path.getmtime(path)
        except Exception:
            pass
    return None

_WRAPPER_TAGS = re.compile(
    r'</?(?:USER_REQUEST|ADDITIONAL_METADATA|USER_SETTINGS_CHANGE|SYSTEM_REMINDERS)[^>]*>',
    re.IGNORECASE
)

def clean_user_content(raw: str) -> str:
    # Strip the purely wrapper tags themselves, preserving all inner text, XML, and file references
    return _WRAPPER_TAGS.sub('', raw).strip()

def extract_first_user_message(transcript: ConversationTranscript) -> str:
    for step in transcript.steps:
        if step.step_type == TYPE_USER_INPUT:
            return clean_user_content(step.content)
    return ""

def get_date_range(transcript: ConversationTranscript):
    dates = [s.created_at for s in transcript.steps if s.created_at]
    if not dates:
        return None, None
    return dates[0], dates[-1]
