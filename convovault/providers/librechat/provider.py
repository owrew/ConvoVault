"""
provider.py
===========
LibreChat provider implementation for ConvoVault (Placeholder).
"""
from __future__ import annotations
import logging
from typing import List, Dict, Optional
from ..base import BaseProvider
from ...models import Conversation, ConversationMeta
from ...config.exporter import ExporterConfig

log = logging.getLogger(__name__)

class LibreChatProvider(BaseProvider):
    @property
    def name(self) -> str:
        return "librechat"

    def discover_conversations(self, config: ExporterConfig) -> List[str]:
        log.warning("LibreChat provider discovery is currently planned but not yet active.")
        return []

    def read_conversation(self, conv_id: str, config: ExporterConfig) -> Optional[Conversation]:
        return None

    def load_metadata_index(self, config: ExporterConfig) -> Dict[str, ConversationMeta]:
        return {}
