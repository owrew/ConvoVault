"""Compatibility helpers backed by the portable claude reader."""
from ..portable import adapter, text_content
from ...config.exporter import ExporterConfig


def read_claude_export(filepath):
    reader = adapter("claude")()
    config = ExporterConfig(filepath, ".", "claude")
    reader.load_metadata_index(config)
    return list(reader._conversations.values())


def _extract_claude_text(msg):
    return text_content(msg.get("content")) or msg.get("text", "")
