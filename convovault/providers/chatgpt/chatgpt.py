"""Compatibility helpers backed by the portable chatgpt reader."""
from ..portable import adapter, chatgpt_steps
from ...config.exporter import ExporterConfig


def read_chatgpt_export(filepath):
    reader = adapter("chatgpt")()
    config = ExporterConfig(filepath, ".", "chatgpt")
    reader.load_metadata_index(config)
    return list(reader._conversations.values())


def _flatten_chatgpt_tree(mapping, current_node=None):
    return chatgpt_steps(mapping, current_node)
