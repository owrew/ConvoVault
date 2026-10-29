"""Conservative source discovery: known transcript paths only, no account caches."""
import os
import sys
from pathlib import Path


def discover_sources(home=None):
    home = Path(home or Path.home())
    codex = Path(os.environ.get("CODEX_HOME", home / ".codex"))
    appdata = Path(os.environ.get("APPDATA", home / ".config"))
    candidates = [
        ("codex", "Codex desktop & CLI", codex, "Local sessions and archived sessions"),
        ("claude-code", "Claude Code", home / ".claude" / "projects", "Local JSONL transcripts"),
        ("gemini", "Gemini CLI", home / ".gemini" / "tmp", "Local session JSON files"),
        ("antigravity", "Google Antigravity", home / ".gemini" / "antigravity", "Brain, summaries and SQLite"),
        ("openwebui", "Open WebUI", home / ".local/share/open-webui/webui.db", "Read-only SQLite"),
        ("openwebui", "Open WebUI", home / "open-webui/backend/data/webui.db", "Read-only SQLite"),
        ("generic", "LM Studio (portable JSON)", home / ".lmstudio/conversations", "OpenAI-style messages JSON only"),
        ("generic", "LM Studio (portable JSON)", appdata / "LM Studio/conversations", "OpenAI-style messages JSON only"),
    ]
    if sys.platform == "darwin":
        candidates.append(("generic", "LM Studio (portable JSON)", home / "Library/Application Support/LM Studio/conversations", "OpenAI-style messages JSON only"))
    return [{"provider": p, "label": label, "path": str(path), "exists": path.exists(), "detail": detail}
            for p, label, path, detail in candidates]


EXPORT_SOURCES = [
    {"provider": "chatgpt", "label": "ChatGPT", "detail": "Choose official conversations.json or export ZIP. Desktop account caches are not a portable history."},
    {"provider": "claude", "label": "Claude.ai", "detail": "Choose conversations.json or export ZIP."},
    {"provider": "librechat", "label": "LibreChat", "detail": "Choose JSON export with messages and conversationId."},
    {"provider": "generic", "label": "Other assistants", "detail": "Import portable JSON with title and messages[{role, content}]. Perplexity, Copilot and other account caches are not automatically decoded."},
]
