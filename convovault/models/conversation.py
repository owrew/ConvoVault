"""
conversation.py
===============
Universal data models for ConvoVault.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolCall:
    name: str
    args: Dict[str, Any]
    tool_summary: str = ""
    tool_action: str = ""

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> ToolCall:
        args = d.get("args", {})
        return cls(
            name=d.get("name", "unknown"),
            args=args,
            tool_summary=args.get("toolSummary", ""),
            tool_action=args.get("toolAction", ""),
        )


@dataclass
class Step:
    index: int
    source: str            # USER_EXPLICIT | MODEL | SYSTEM
    step_type: str         # USER_INPUT | PLANNER_RESPONSE | VIEW_FILE | etc.
    status: str
    created_at: str        # ISO 8601 timestamp
    content: str = ""
    thinking: str = ""
    tool_calls: List[ToolCall] = field(default_factory=list)
    truncated: bool = False


@dataclass
class ConversationMeta:
    conversation_id: str
    title: str
    step_count: int = 0
    created_at: Optional[int] = None   # Unix timestamp
    updated_at: Optional[int] = None   # Unix timestamp
    trajectory_id: Optional[str] = None
    last_viewed_at: Optional[int] = None # Unix timestamp


@dataclass
class Turn:
    num: int
    source: str            # User | Assistant
    timestamp: str         # ISO 8601 or empty
    steps: List[Step] = field(default_factory=list)


@dataclass
class ConversationIntelligence:
    summary: str = ""
    topics: List[str] = field(default_factory=list)
    technologies: List[str] = field(default_factory=list)
    files_mentioned: List[str] = field(default_factory=list)
    commands_executed: List[str] = field(default_factory=list)
    code_languages: List[str] = field(default_factory=list)


@dataclass
class Conversation:
    conv_id: str
    provider: str
    steps: List[Step]
    source_file: str
    meta: Optional[ConversationMeta] = None
    turns: List[Turn] = field(default_factory=list)
    intelligence: ConversationIntelligence = field(default_factory=ConversationIntelligence)
    related_ids: List[str] = field(default_factory=list)


# Backward compatibility alias
ConversationTranscript = Conversation
