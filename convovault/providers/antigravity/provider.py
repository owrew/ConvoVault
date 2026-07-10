"""
provider.py
===========
Antigravity provider implementation for ConvoVault.
"""
from __future__ import annotations
import os
from typing import List, Dict, Optional
from ..base import BaseProvider
from ...models import Conversation, ConversationMeta
from ...config.exporter import ExporterConfig

from .transcript import read_transcript, get_transcript_mtime
from .pb_summaries import parse_summaries
from .annotations import parse_annotation
from .sqlite_db import read_from_sqlite

class AntigravityProvider(BaseProvider):
    @property
    def name(self) -> str:
        return "antigravity"

    def discover_conversations(self, config: ExporterConfig) -> List[str]:
        ids = set()
        if os.path.isdir(config.conversations_dir):
            for fname in os.listdir(config.conversations_dir):
                if fname.endswith('.db'):
                    ids.add(fname[:-3])
                    
        if os.path.isdir(config.brain_dir):
            for name in os.listdir(config.brain_dir):
                logs_dir = os.path.join(config.brain_dir, name, '.system_generated', 'logs')
                if os.path.isdir(logs_dir):
                    ids.add(name)
                    
        return sorted(list(ids))

    def read_conversation(self, conv_id: str, config: ExporterConfig) -> Optional[Conversation]:
        # 1. Read JSONL (Primary)
        ts = read_transcript(config.brain_dir, conv_id)
        if ts:
            ts.provider = self.name
            return ts
            
        # 2. Fallback to SQLite
        db_path = os.path.join(config.conversations_dir, conv_id + ".db")
        if os.path.isfile(db_path):
            ts = read_from_sqlite(db_path, conv_id)
            if ts:
                ts.provider = self.name
                return ts
        return None

    def load_metadata_index(self, config: ExporterConfig) -> Dict[str, ConversationMeta]:
        meta_index = parse_summaries(config.summaries_pb_path)
        for cid, meta in meta_index.items():
            annot_path = os.path.join(config.annotations_dir, cid + ".pbtxt")
            last_view = parse_annotation(annot_path)
            if last_view:
                meta.last_viewed_at = last_view
        return meta_index

