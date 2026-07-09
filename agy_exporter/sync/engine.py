"""
engine.py
=========
Orchestration engine coordinating loaders, analyzers, renderer, and indexers.
"""
from __future__ import annotations
import os
import re
import logging
from typing import Dict, List, Optional, Set

from ..models import ConversationTranscript, ConversationMeta
from ..config import ExporterConfig
from ..sources.transcript import read_transcript, get_transcript_mtime
from ..sources.pb_summaries import parse_summaries
from ..sources.annotations import parse_annotation
from ..sources.sqlite_db import read_from_sqlite
from ..analysis.intelligence import generate_intelligence
from ..analysis.relations import find_relations
from ..render.conversation import format_conversation
from ..analysis.wikilinks import title_to_filename
from ..render.index import generate_indexes
from .state import ExportState, get_content_hash

log = logging.getLogger(__name__)

DEBUG_SUBDIR = ".agy_debug"

def discover_conversations(config: ExporterConfig) -> List[str]:
    ids: Set[str] = set()
    
    if os.path.isdir(config.conversations_dir):
        for fname in os.listdir(config.conversations_dir):
            if fname.endswith('.db'):
                ids.add(fname[:-3])
                
    if os.path.isdir(config.brain_dir):
        for name in os.listdir(config.brain_dir):
            logs_dir = os.path.join(config.brain_dir, name, '.system_generated', 'logs')
            if os.path.isdir(logs_dir):
                ids.add(name)
                
    result = sorted(list(ids))
    log.info("Discovered %d conversation IDs", len(result))
    return result

def load_transcript_for_id(conv_id: str, config: ExporterConfig) -> Optional[ConversationTranscript]:
    db_path = os.path.join(config.conversations_dir, conv_id + ".db")
    
    # 1. Read JSONL (Primary)
    transcript = read_transcript(config.brain_dir, conv_id)
    
    # 2. Fallback to SQLite
    if transcript is None or not transcript.steps:
        if os.path.isfile(db_path):
            log.debug("Transcript files missing/empty for %s, falling back to SQLite", conv_id)
            transcript = read_from_sqlite(db_path, conv_id)
            
    return transcript

def export_one(
    conv_id: str,
    transcript: ConversationTranscript,
    config: ExporterConfig,
    meta_index: Dict[str, ConversationMeta],
    state: ExportState,
    all_meta: Dict[str, ConversationMeta]
) -> Optional[bool]:  # True=written, False=skipped, None=error
    meta = meta_index.get(conv_id)
    db_path = os.path.join(config.conversations_dir, conv_id + ".db")
    
    # Check source file modification time
    source_mtime = None
    if 'transcript_full' in transcript.source_file or 'transcript.jsonl' in transcript.source_file:
        source_mtime = get_transcript_mtime(config.brain_dir, conv_id)
    elif transcript.source_file.endswith('.db'):
        source_mtime = os.path.getmtime(db_path)

    # Load view time from annotations
    annot_path = os.path.join(config.annotations_dir, conv_id + ".pbtxt")
    last_view = parse_annotation(annot_path)
    if meta and last_view:
        meta.last_viewed_at = last_view

    # Format Markdown
    try:
        md_content = format_conversation(
            transcript=transcript,
            meta=meta,
            all_meta=all_meta,
            config=config
        )
    except Exception as e:
        log.error("Formatting failed for %s: %s", conv_id, e)
        if config.debug:
            _dump_debug(conv_id, transcript, config.vault_dir, str(e))
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

def _dump_debug(conv_id: str, transcript: ConversationTranscript, vault_dir: str, err: str):
    debug_dir = os.path.join(vault_dir, DEBUG_SUBDIR)
    os.makedirs(debug_dir, exist_ok=True)
    out_path = os.path.join(debug_dir, conv_id + ".txt")
    try:
        with open(out_path, 'w', encoding='utf-8') as fh:
            fh.write(f"DECODE ERROR: {err}\n\n")
            fh.write(f"Source file: {transcript.source_file}\n")
            fh.write(f"Steps count: {len(transcript.steps)}\n\n")
            for step in transcript.steps[:20]:
                fh.write(f"--- Step {step.index} Type={step.step_type} ---\n")
                fh.write(step.content[:1000] if step.content else "[empty]")
                fh.write("\n\n")
    except Exception:
        pass

def run_export(config: ExporterConfig) -> dict:
    log.info("Starting Antigravity -> Obsidian sync engine")
    
    # 1. Parse summaries pb (holds titles)
    meta_index = parse_summaries(config.summaries_pb_path)
    
    # 2. Discover conversation IDs
    conv_ids = discover_conversations(config)
    if config.conv_filter:
        conv_ids = [c for c in conv_ids if c in config.conv_filter]

    # Populate missing titles with fallbacks in meta_index
    for cid in conv_ids:
        if cid not in meta_index:
            meta_index[cid] = ConversationMeta(conversation_id=cid, title=cid[:8])

    # 3. Load transcripts and run intelligence/relations in memory
    transcripts: Dict[str, ConversationTranscript] = {}
    stats = {'written': 0, 'skipped': 0, 'failed': 0, 'total': len(conv_ids)}
    
    log.info("Loading and analyzing transcripts...")
    for cid in conv_ids:
        try:
            ts = load_transcript_for_id(cid, config)
            if ts and ts.steps:
                ts.meta = meta_index.get(cid)
                ts.intelligence = generate_intelligence(ts)
                transcripts[cid] = ts
            else:
                log.warning("No transcript data available for %s", cid)
                stats['failed'] += 1
        except Exception as e:
            log.error("Failed loading conversation %s: %s", cid, e, exc_info=True)
            stats['failed'] += 1

    # 3b. Eagerly load annotations for all conversations so last_viewed is always
    #     populated before any rendering — this keeps content hashes stable across runs.
    for cid in conv_ids:
        meta = meta_index.get(cid)
        if meta and not meta.last_viewed_at:
            annot_path = os.path.join(config.annotations_dir, cid + ".pbtxt")
            last_view = parse_annotation(annot_path)
            if last_view:
                meta.last_viewed_at = last_view

    # 4. Cross-link relations
    find_relations(transcripts)

    # 5. Export Markdown documents (Idempotent)
    state = ExportState(config.vault_dir)
    
    for cid, ts in transcripts.items():
        try:
            res = export_one(
                conv_id=cid,
                transcript=ts,
                config=config,
                meta_index=meta_index,
                state=state,
                all_meta=meta_index
            )
            if res is True:
                stats['written'] += 1
            elif res is False:
                stats['skipped'] += 1
            else:  # None = error
                stats['failed'] += 1
        except Exception as e:
            log.error("Failed exporting conversation %s: %s", cid, e, exc_info=True)
            stats['failed'] += 1

    # 6. Save State
    state.save()

    # 7. Generate global index files
    log.info("Rebuilding Timeline, Topics, Tag, and Conversation indexes...")
    generate_indexes(config.vault_dir, transcripts)

    log.info(
        "Engine completed. Total=%d  Written=%d  Skipped=%d  Failed=%d",
        stats['total'], stats['written'], stats['skipped'], stats['failed']
    )
    return stats
