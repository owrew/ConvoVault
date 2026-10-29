"""
engine.py
=========
Provider-independent synchronization engine coordinating loaders, analyzers,
renderer, and indexers.
"""
from __future__ import annotations
import os
import logging
from typing import Dict, Optional

from ..models import Conversation, ConversationMeta
from ..config.exporter import ExporterConfig
from ..rendering.conversation import format_conversation
from ..analysis.wikilinks import title_to_filename
from ..state.state import ExportState, get_content_hash

log = logging.getLogger(__name__)

DEBUG_SUBDIR = ".convovault_debug"


def export_one(
    conv_id: str,
    convo: Conversation,
    config: ExporterConfig,
    meta_index: Dict[str, ConversationMeta],
    state: ExportState,
    all_meta: Dict[str, ConversationMeta]
) -> Optional[bool]:  # True=written, False=skipped, None=error
    meta = meta_index.get(conv_id)

    # Check source file modification time
    source_mtime = None
    if convo.source_file and os.path.isfile(convo.source_file):
        try:
            source_mtime = os.path.getmtime(convo.source_file)
        except Exception:
            pass

    # Format Markdown
    try:
        md_content = format_conversation(
            transcript=convo,
            meta=meta,
            all_meta=all_meta,
            config=config
        )
    except Exception as e:
        log.error("Formatting failed for %s: %s", conv_id, e)
        if config.debug:
            _dump_debug(conv_id, convo, config.vault_dir, str(e))
        return None

    # Idempotency check — skip write if content and mtime unchanged
    chash = get_content_hash(md_content)
    if not config.force and not state.needs_update(conv_id, chash, source_mtime):
        log.debug("Up-to-date, skipping: %s", conv_id[:8])
        return False  # sentinel: skipped

    # Filename collision resolver
    title = meta.title if meta else conv_id[:8]
    filename = title_to_filename(title)

    existing_path = state.get_note_path(conv_id)
    if existing_path:
        filename = os.path.basename(existing_path)
    else:
        candidate = os.path.join(config.output_chats_dir, filename)
        counter = 1
        while os.path.isfile(candidate):
            try:
                with open(candidate, 'r', encoding='utf-8') as fh:
                    first_lines = fh.read(500)
                if conv_id not in first_lines:
                    stem = filename[:-3]
                    filename = f"{stem} ({counter}).md"
                    candidate = os.path.join(config.output_chats_dir, filename)
                    counter += 1
                else:
                    break
            except Exception:
                break

    os.makedirs(config.output_chats_dir, exist_ok=True)
    note_path = os.path.join(config.output_chats_dir, filename)

    try:
        with open(note_path, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(md_content)
        log.info("Synced: %s -> %s", conv_id[:8], filename)
    except Exception as e:
        log.error("Failed writing Obsidian note for %s: %s", conv_id, e)
        return None

    state.mark_exported(conv_id, chash, source_mtime, note_path)
    return True  # sentinel: written


def _dump_debug(conv_id: str, convo: Conversation, vault_dir: str, err: str):
    debug_dir = os.path.join(vault_dir, DEBUG_SUBDIR)
    os.makedirs(debug_dir, exist_ok=True)
    out_path = os.path.join(debug_dir, conv_id + ".txt")
    try:
        with open(out_path, 'w', encoding='utf-8') as fh:
            fh.write(f"DECODE ERROR: {err}\n\n")
            fh.write(f"Source file: {convo.source_file}\n")
            fh.write(f"Steps count: {len(convo.steps)}\n\n")
            for step in convo.steps[:20]:
                fh.write(f"--- Step {step.index} Type={step.step_type} ---\n")
                fh.write(step.content[:1000] if step.content else "[empty]")
                fh.write("\n\n")
    except Exception:
        pass


def run_export(config: ExporterConfig) -> dict:
    from ..workspace import export_library
    return export_library(config)
