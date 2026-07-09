"""
claude_ai.py
============
Source reader for Claude.ai conversation exports.

Usage:
  Claude.ai → Settings → Privacy → Export Data
  Download and extract → find conversations.json
  Then run:
    python -m agy_exporter --source-app claude --claude-file conversations.json
"""
from __future__ import annotations
import json
import logging
import os
from typing import List
from ..models import Step, ConversationTranscript

log = logging.getLogger(__name__)


def read_claude_export(filepath: str) -> List[ConversationTranscript]:
    """
    Parse a Claude.ai conversations.json export file.

    Claude exports a JSON array where each element is a conversation with:
      - uuid: str
      - name: str
      - created_at: ISO timestamp
      - updated_at: ISO timestamp
      - chat_messages: list of message objects
        Each message:
          - uuid: str
          - sender: 'human' | 'assistant'
          - text: str (may be empty if content array is used)
          - content: list of content blocks [{type, text}]
          - created_at: ISO timestamp
    """
    if not os.path.isfile(filepath):
        log.error("Claude export file not found: %s", filepath)
        return []

    try:
        with open(filepath, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
    except Exception as e:
        log.error("Failed to parse Claude export: %s", e)
        return []

    transcripts: List[ConversationTranscript] = []

    for convo in data:
        conv_id = convo.get('uuid', '')
        title = convo.get('name', conv_id[:8] or 'Untitled')
        messages = convo.get('chat_messages', [])

        steps: List[Step] = []
        for idx, msg in enumerate(messages):
            sender = msg.get('sender', '')
            # Prefer content blocks, fall back to text field
            text = _extract_claude_text(msg)
            if not text:
                continue

            if sender == 'human':
                step_type = 'USER_INPUT'
            elif sender == 'assistant':
                step_type = 'PLANNER_RESPONSE'
            else:
                continue

            steps.append(Step(
                index=idx,
                source=sender.upper(),
                step_type=step_type,
                status='DONE',
                created_at=msg.get('created_at', ''),
                content=text,
            ))

        if not steps:
            continue

        ts = ConversationTranscript(
            conv_id=conv_id,
            steps=steps,
            source_file=filepath,
        )
        ts._claude_title = title
        transcripts.append(ts)

    log.info("Loaded %d Claude conversations from %s", len(transcripts), filepath)
    return transcripts


def _extract_claude_text(msg: dict) -> str:
    """Extract text from a Claude message, handling both text field and content blocks."""
    # Try content blocks first (richer format)
    content = msg.get('content', [])
    if content and isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get('type') == 'text':
                    parts.append(block.get('text', ''))
                elif block.get('type') == 'tool_use':
                    name = block.get('name', 'tool')
                    inp = json.dumps(block.get('input', {}), indent=2)
                    parts.append(f"[Tool: {name}]\n{inp}")
                elif block.get('type') == 'tool_result':
                    result = block.get('content', '')
                    if isinstance(result, list):
                        result = '\n'.join(b.get('text', '') for b in result if isinstance(b, dict))
                    parts.append(f"[Tool Result]\n{result}")
        text = '\n'.join(p for p in parts if p)
        if text:
            return text

    # Fall back to plain text field
    return msg.get('text', '')
