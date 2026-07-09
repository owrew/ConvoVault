"""
chatgpt.py
==========
Source reader for ChatGPT conversation exports.

Usage:
  ChatGPT → Settings → Data Controls → Export Data
  Download the zip → extract conversations.json
  Then run:
    python -m agy_exporter --source-app chatgpt --chatgpt-file conversations.json
"""
from __future__ import annotations
import json
import logging
import os
from typing import Dict, List, Optional
from ..models import Step, ToolCall, ConversationTranscript

log = logging.getLogger(__name__)


def read_chatgpt_export(filepath: str) -> List[ConversationTranscript]:
    """
    Parse a ChatGPT conversations.json export file into ConversationTranscripts.

    The file is a JSON array of conversation objects. Each conversation has:
      - id: UUID
      - title: str
      - create_time: float (unix)
      - update_time: float (unix)
      - mapping: dict of node_id -> message nodes (tree structure)
    """
    if not os.path.isfile(filepath):
        log.error("ChatGPT export file not found: %s", filepath)
        return []

    try:
        with open(filepath, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
    except Exception as e:
        log.error("Failed to parse ChatGPT export: %s", e)
        return []

    transcripts: List[ConversationTranscript] = []

    for convo in data:
        conv_id = convo.get('id', '')
        title = convo.get('title', conv_id[:8] or 'Untitled')
        mapping: dict = convo.get('mapping', {})

        # Flatten tree into linear message list using parent pointers
        steps = _flatten_chatgpt_tree(mapping)

        if not steps:
            continue

        ts = ConversationTranscript(
            conv_id=conv_id,
            steps=steps,
            source_file=filepath,
        )
        # Attach a minimal meta with title
        ts._chatgpt_title = title  # accessed by engine wrapper
        transcripts.append(ts)

    log.info("Loaded %d ChatGPT conversations from %s", len(transcripts), filepath)
    return transcripts


def _flatten_chatgpt_tree(mapping: dict) -> List[Step]:
    """Walk the message tree in conversation order and produce Steps."""
    # Find root node (no parent)
    root_id = None
    for node_id, node in mapping.items():
        if node.get('parent') is None:
            root_id = node_id
            break

    if root_id is None:
        return []

    # BFS / DFS to get ordered messages
    ordered_ids: List[str] = []
    stack = [root_id]
    while stack:
        nid = stack.pop(0)
        ordered_ids.append(nid)
        children = mapping.get(nid, {}).get('children', [])
        stack.extend(children)

    steps: List[Step] = []
    for idx, nid in enumerate(ordered_ids):
        node = mapping.get(nid, {})
        msg = node.get('message')
        if not msg:
            continue

        author_role = msg.get('author', {}).get('role', '')
        content_obj = msg.get('content', {})
        parts = content_obj.get('parts', [])
        text = '\n'.join(str(p) for p in parts if isinstance(p, str) and p.strip())

        if not text:
            continue

        if author_role == 'user':
            step_type = 'USER_INPUT'
        elif author_role == 'assistant':
            step_type = 'PLANNER_RESPONSE'
        elif author_role == 'tool':
            step_type = 'RUN_COMMAND'  # closest match
        else:
            continue

        create_ts = msg.get('create_time')
        iso = ''
        if create_ts:
            from datetime import datetime, timezone
            iso = datetime.fromtimestamp(float(create_ts), tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

        steps.append(Step(
            index=idx,
            source=author_role.upper(),
            step_type=step_type,
            status='DONE',
            created_at=iso,
            content=text,
        ))

    return steps
