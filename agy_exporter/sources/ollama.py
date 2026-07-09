"""
ollama.py
=========
Source reader for Ollama conversation history.

Ollama stores chat history in different places depending on which
front-end you use:

  - Open WebUI  → SQLite at ~/.local/share/open-webui/webui.db
  - Ollama CLI  → No built-in history (sessions are stateless)
  - LM Studio   → JSON files in ~/Library/Application Support/LM Studio/
  - Jan         → JSON files in ~/jan/threads/

This reader covers Open WebUI (most common) and a generic JSON format.

Usage:
  python -m agy_exporter --source-app ollama --ollama-db ~/.local/share/open-webui/webui.db

  # Or if you have JSON exports:
  python -m agy_exporter --source-app ollama --ollama-json /path/to/export.json
"""
from __future__ import annotations
import json
import logging
import os
from typing import List, Optional
from ..models import Step, ConversationTranscript

log = logging.getLogger(__name__)


def read_open_webui_db(db_path: str) -> List[ConversationTranscript]:
    """
    Read conversations from Open WebUI's SQLite database.
    Table: chat  columns: id, user_id, title, chat (JSON blob), created_at, updated_at
    """
    try:
        import sqlite3
    except ImportError:
        log.error("sqlite3 not available")
        return []

    if not os.path.isfile(db_path):
        log.error("Open WebUI database not found: %s", db_path)
        return []

    transcripts: List[ConversationTranscript] = []
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT id, title, chat, created_at FROM chat ORDER BY created_at")
        for row in cur:
            conv_id = str(row['id'])
            title = row['title'] or conv_id[:8]
            try:
                chat_data = json.loads(row['chat'] or '{}')
            except Exception:
                continue

            messages = chat_data.get('messages', [])
            steps = _parse_openwebui_messages(messages)
            if not steps:
                continue

            ts = ConversationTranscript(conv_id=conv_id, steps=steps, source_file=db_path)
            ts._ollama_title = title
            transcripts.append(ts)
        conn.close()
    except Exception as e:
        log.error("Failed reading Open WebUI DB %s: %s", db_path, e)

    log.info("Loaded %d Ollama/Open WebUI conversations", len(transcripts))
    return transcripts


def _parse_openwebui_messages(messages: list) -> List[Step]:
    steps: List[Step] = []
    for idx, msg in enumerate(messages):
        role = msg.get('role', '')
        content = msg.get('content', '')
        if isinstance(content, list):
            content = '\n'.join(
                b.get('text', '') for b in content
                if isinstance(b, dict) and b.get('type') == 'text'
            )
        if not content:
            continue

        if role == 'user':
            step_type = 'USER_INPUT'
        elif role == 'assistant':
            step_type = 'PLANNER_RESPONSE'
        else:
            continue

        # Open WebUI timestamps may be unix or ISO
        ts = msg.get('timestamp') or msg.get('created_at', '')
        if isinstance(ts, (int, float)):
            from datetime import datetime, timezone
            ts = datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

        model = msg.get('model', '')
        if model:
            content = f"*Model: {model}*\n\n{content}"

        steps.append(Step(
            index=idx,
            source=role.upper(),
            step_type=step_type,
            status='DONE',
            created_at=str(ts),
            content=content,
        ))
    return steps


def read_lm_studio_export(folder: str) -> List[ConversationTranscript]:
    """
    Read LM Studio conversation JSON files from a directory.
    LM Studio saves each conversation as a .json file in:
      ~/Library/Application Support/LM Studio/conversations/  (macOS)
      %APPDATA%\LM Studio\conversations\                       (Windows)
    """
    transcripts: List[ConversationTranscript] = []
    if not os.path.isdir(folder):
        log.error("LM Studio folder not found: %s", folder)
        return []

    for fname in os.listdir(folder):
        if not fname.endswith('.json'):
            continue
        fpath = os.path.join(folder, fname)
        try:
            with open(fpath, 'r', encoding='utf-8') as fh:
                data = json.load(fh)
        except Exception:
            continue

        conv_id = data.get('id', fname[:-5])
        title = data.get('title', conv_id[:8])
        messages = data.get('messages', [])
        steps = _parse_openwebui_messages(messages)  # same format
        if not steps:
            continue

        ts = ConversationTranscript(conv_id=conv_id, steps=steps, source_file=fpath)
        ts._ollama_title = title
        transcripts.append(ts)

    log.info("Loaded %d LM Studio conversations from %s", len(transcripts), folder)
    return transcripts
