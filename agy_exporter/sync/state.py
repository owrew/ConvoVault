"""
state.py
========
Idempotency and export state manager tracking content hashes and note paths.
"""
from __future__ import annotations
import json
import logging
import os
import hashlib
from datetime import datetime, timezone
from typing import Dict, Optional, Set

log = logging.getLogger(__name__)

STATE_FILE = ".agy_export_state.json"

class ExportState:
    def __init__(self, vault_dir: str):
        self.vault_dir = vault_dir
        self.path = os.path.join(vault_dir, STATE_FILE)
        self.state: Dict[str, dict] = {}
        self.load()

    def load(self):
        if os.path.isfile(self.path):
            try:
                with open(self.path, 'r', encoding='utf-8') as fh:
                    self.state = json.load(fh)
                log.debug("Loaded export state containing %d entries", len(self.state))
            except Exception as e:
                log.warning("Could not load export state: %s", e)

    def save(self):
        try:
            with open(self.path, 'w', encoding='utf-8') as fh:
                json.dump(self.state, fh, indent=2)
            log.debug("Saved export state containing %d entries", len(self.state))
        except Exception as e:
            log.error("Could not save export state: %s", e)

    def needs_update(self, conv_id: str, content_hash: str, mtime: Optional[float]) -> bool:
        entry = self.state.get(conv_id, {})
        if not entry:
            return True
            
        # Check if the output file still exists where we wrote it
        note_path = entry.get('note_path')
        if not note_path or not os.path.isfile(note_path):
            log.debug("Note file missing at %s, forcing re-export", note_path)
            return True

        if entry.get('content_hash') != content_hash:
            log.debug("Hash mismatch for %s: local=%s, incoming=%s", conv_id[:8], entry.get('content_hash'), content_hash)
            return True
            
        if mtime is not None and entry.get('source_mtime') != mtime:
            log.debug("Mtime mismatch for %s: local=%s, incoming=%s", conv_id[:8], entry.get('source_mtime'), mtime)
            return True

        return False

    def mark_exported(self, conv_id: str, content_hash: str, mtime: Optional[float], note_path: str):
        self.state[conv_id] = {
            'content_hash': content_hash,
            'source_mtime': mtime,
            'note_path': note_path,
            'exported_at': datetime.now(tz=timezone.utc).isoformat(),
        }

    def get_note_path(self, conv_id: str) -> Optional[str]:
        return self.state.get(conv_id, {}).get('note_path')

    def all_exported_paths(self) -> Set[str]:
        return {v['note_path'] for v in self.state.values() if 'note_path' in v}

def get_content_hash(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]
