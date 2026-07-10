"""
base.py
=======
Base provider interface for all AI conversation sources.
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from ..models import Conversation, ConversationMeta
from ..config.exporter import ExporterConfig

class BaseProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the unique lowercase name of this provider (e.g., 'antigravity')."""
        pass

    @abstractmethod
    def discover_conversations(self, config: ExporterConfig) -> List[str]:
        """Discover and return conversation IDs available for this provider."""
        pass

    @abstractmethod
    def read_conversation(self, conv_id: str, config: ExporterConfig) -> Optional[Conversation]:
        """Read, normalize, and return the common Conversation model."""
        pass

    @abstractmethod
    def load_metadata_index(self, config: ExporterConfig) -> Dict[str, ConversationMeta]:
        """Load and return metadata/summaries for all conversations of this provider."""
        pass
