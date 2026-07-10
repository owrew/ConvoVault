"""
provider.py
===========
ChatGPT provider implementation for ConvoVault.
"""
from __future__ import annotations
import os
from typing import List, Dict, Optional
from ..base import BaseProvider
from ...models import Conversation, ConversationMeta
from ...config.exporter import ExporterConfig
from .chatgpt import read_chatgpt_export

class ChatGPTProvider(BaseProvider):
    _cached_filepath: Optional[str] = None
    _cached_convs: Dict[str, Conversation] = {}

    @property
    def name(self) -> str:
        return "chatgpt"

    def _get_filepath(self, config: ExporterConfig) -> Optional[str]:
        # Check if source_dir is the conversations.json file or contains it
        if os.path.isfile(config.source_dir) and config.source_dir.endswith(".json"):
            return config.source_dir
        candidate = os.path.join(config.source_dir, "conversations.json")
        if os.path.isfile(candidate):
            return candidate
        return None

    def _load_all(self, config: ExporterConfig):
        filepath = self._get_filepath(config)
        if not filepath:
            return
        if self._cached_filepath == filepath and self._cached_convs:
            return
        
        convs = read_chatgpt_export(filepath)
        self._cached_convs = {c.conv_id: c for c in convs}
        self._cached_filepath = filepath

    def discover_conversations(self, config: ExporterConfig) -> List[str]:
        self._load_all(config)
        return sorted(list(self._cached_convs.keys()))

    def read_conversation(self, conv_id: str, config: ExporterConfig) -> Optional[Conversation]:
        self._load_all(config)
        ts = self._cached_convs.get(conv_id)
        if ts:
            ts.provider = self.name
            # If meta is not set, synthesize it
            if not ts.meta:
                title = getattr(ts, "_chatgpt_title", conv_id[:8])
                ts.meta = ConversationMeta(
                    conversation_id=conv_id,
                    title=title,
                    step_count=len(ts.steps),
                )
            return ts
        return None

    def load_metadata_index(self, config: ExporterConfig) -> Dict[str, ConversationMeta]:
        self._load_all(config)
        index = {}
        for cid, ts in self._cached_convs.items():
            title = getattr(ts, "_chatgpt_title", cid[:8])
            index[cid] = ConversationMeta(
                conversation_id=cid,
                title=title,
                step_count=len(ts.steps),
            )
        return index
