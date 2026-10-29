# Supported sources in 3.0

Source discovery checks known paths rather than searching browser profiles, cookies, tokens, or encrypted application databases. Paths can be overridden in the GUI or CLI. A detected directory is not proof that it contains a supported transcript.

| Source | Import format | Discovery / limits |
| --- | --- | --- |
| Codex desktop and CLI | Local rollout JSONL; response-item messages, function calls/outputs and event-message fallback | `CODEX_HOME` or `~/.codex`; `sessions` and `archived_sessions`; names from `session_index.jsonl` |
| ChatGPT | Official `conversations.json`, directly or inside an export ZIP | User chooses export; follows `current_node` parent chain; latest leaf fallback if absent; alternatives remain in original export |
| Claude.ai | `conversations.json` or export ZIP, with `chat_messages` | User chooses export; human/assistant text and tool-use blocks |
| Claude Code | Local project JSONL transcripts | `~/.claude/projects`; duplicate record UUIDs ignored; tool-only user envelopes remain tools |
| Gemini CLI | `session-*.json`, `sessionId`, `messages` with `type:user/gemini` | `~/.gemini/tmp`; a single JSON file can also be selected |
| Google Antigravity | Existing JSONL brain logs, protobuf summaries, SQLite fallback | `~/.gemini/antigravity`; existing decoding retained |
| Open WebUI | SQLite `chat` table with JSON `messages` | Common user-local data locations; choose custom database paths manually; read-only connection |
| LibreChat | JSON conversation objects with `conversationId`, `messages`, and `isCreatedByUser` or role/content | User-supplied portable exports; native server databases are not queried |
| LM Studio / Ollama frontends | Portable JSON objects with `messages` | Checks common LM Studio folders; proprietary LM Studio save formats are not claimed supported; Ollama itself is not treated as a history store |
| Other assistants | Documented generic role/content JSON | Manual import; no automatic Perplexity, Copilot, or other proprietary cache decoding |

Gemini web Takeout HTML, native Jan/LM Studio proprietary files, ChatGPT desktop account caches, and encrypted reasoning are not decoded. Media is represented by attachment markers when recognizable, not copied into the vault.

The JSON and ZIP member limit is 512 MB. ZIPs are read without extracting arbitrary members. Large exports are parsed in memory; use smaller exports for very large archives. JSONL is streamed line by line, but normalized conversations are held in memory for preview/export.

## Generic JSON example

```json
[
  {
    "id": "my-stable-conversation-id",
    "title": "Planning a project",
    "created_at": "2026-10-29T08:00:00Z",
    "messages": [
      {"role": "user", "content": "Help me organize this project."},
      {"role": "assistant", "content": "Start with the outcome and the first small milestone."}
    ]
  }
]
```

Single conversation objects and `{ "conversations": [...] }` or `{ "chats": [...] }` containers are supported. Messages accept text strings or text/content block arrays. Roles include user, assistant, tool, system, and developer. Legacy human/model roles are normalized.

The included `examples/studio-demo.json` is synthetic sample content for trying the GUI without importing personal chats.
