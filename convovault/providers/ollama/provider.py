"""
provider.py
===========
Ollama / LM Studio provider implementation for ConvoVault.
"""
from __future__ import annotations
import os
from typing import List, Dict, Optional
from ..base import BaseProvider
from ...models import Conversation, ConversationMeta
from ...config.exporter import ExporterConfig
from .ollama import read_lm_studio_export

class OllamaProvider(BaseProvider):
    _cached_folder: Optional[str] = None
    _cached_convs: Dict[str, Conversation] = {}

    @property
    def name(self) -> str:
        return "ollama"

    def _load_all(self, config: ExporterConfig):
        folder = config.source_dir
        if not os.path.isdir(folder):
            return
        if self._cached_folder == folder and self._cached_convs:
            return
        
        convs = read_lm_studio_export(folder)
        self._cached_convs = {c.conv_id: c for c in convs}
        self._cached_folder = folder

    def discover_conversations(self, config: ExporterConfig) -> List[str]:
        self._load_all(config)
        return sorted(list(self._cached_convs.keys()))

    def read_conversation(self, conv_id: str, config: ExporterConfig) -> Optional[Conversation]:
        self._load_all(config)
        ts = self._cached_convs.get(conv_id)
        if ts:
            ts.provider = self.name
            if not ts.meta:
                title = getattr(ts, "_ollama_title", conv_id[:8])
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
            title = getattr(ts, "_ollama_title", cid[:8])
            index[cid] = ConversationMeta(
                conversation_id=cid,
                title=title,
                step_count=len(ts.steps),
            )
        return index
