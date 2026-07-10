"""
exporter.py
===========
Central configuration for the ConvoVault Exporter.
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class ExporterConfig:
    source_dir: str
    vault_dir: str
    provider: str = "antigravity"
    watch: bool = False
    watch_interval: float = 5.0
    force: bool = False
    debug: bool = False
    conv_filter: Optional[List[str]] = None
    no_tool_results: bool = False
    max_tool_results_per_turn: Optional[int] = None  # None = unlimited
    max_tool_output_length: Optional[int] = None     # None = unlimited
    verbose: bool = False
    
    # Internal paths derived from source_dir and vault_dir (Antigravity/general)
    brain_dir: str = field(init=False)
    conversations_dir: str = field(init=False)
    annotations_dir: str = field(init=False)
    summaries_pb_path: str = field(init=False)
    output_chats_dir: str = field(init=False)
    
    def __post_init__(self):
        self.source_dir = os.path.abspath(self.source_dir)
        self.vault_dir = os.path.abspath(self.vault_dir)
        
        # Derivations needed for the Antigravity provider (retains compatibility)
        self.brain_dir = os.path.join(self.source_dir, "brain")
        self.conversations_dir = os.path.join(self.source_dir, "conversations")
        self.annotations_dir = os.path.join(self.source_dir, "annotations")
        self.summaries_pb_path = os.path.join(self.source_dir, "agyhub_summaries_proto.pb")
        
        self.output_chats_dir = os.path.join(self.vault_dir, "AI Vault", "Chats")
