"""
content.py
==========
Helper functions for cleaning and processing message content.
"""
from __future__ import annotations
import re

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

# Blocks that are purely system-injected metadata — strip tag + content entirely.
_SYSTEM_ONLY_BLOCKS = re.compile(
    r'<(?:ADDITIONAL_METADATA|USER_SETTINGS_CHANGE|SYSTEM_REMINDERS|SYSTEM_MESSAGE)'
    r'[^>]*>.*?</(?:ADDITIONAL_METADATA|USER_SETTINGS_CHANGE|SYSTEM_REMINDERS|SYSTEM_MESSAGE)>',
    re.IGNORECASE | re.DOTALL,
)

# Wrapper tags whose *content* belongs to the user — strip the tag, keep the text.
_WRAPPER_ONLY_TAGS = re.compile(
    r'</?(?:USER_REQUEST)[^>]*>',
    re.IGNORECASE,
)

def clean_user_content(raw: str) -> str:
    """
    Clean a USER_INPUT step's content for display in the exported note.
    """
    if not raw:
        return ""
    # 1. Remove system-only blocks (tag + content)
    text = _SYSTEM_ONLY_BLOCKS.sub('', raw)
    # 2. Strip wrapper-only tags (preserve inner content)
    text = _WRAPPER_ONLY_TAGS.sub('', text)
    # 3. Collapse 3+ consecutive blank lines to 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()
