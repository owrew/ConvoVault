# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- **Full content preservation** — every user message, assistant response, thinking block, tool call, tool output, terminal output, and file content is now included in full by default (no truncation unless explicitly configured)
- `max_tool_output_length` config option and `--max-tool-output-length` CLI flag — set a character limit per tool output block (default: unlimited)
- `max_tool_results_per_turn` now defaults to `None` (unlimited) instead of 5
- `--max-tool-results-per-turn` CLI flag to cap blocks per turn if desired
- `_safe_code_block()` helper — uses adaptive fence length to prevent backtick collisions inside tool outputs
- AI model recognition patterns: **Codex, Qwen, Z AI, Ollama, DeepSeek, Llama, Mistral, Gemma, Local AI** — now tagged and wiki-linked in exported notes
- Eager annotation loading in `run_export` (before rendering) for deterministic `last_viewed` timestamps
- Sorted code language list to prevent set-ordering non-determinism across process runs

### Changed
- `clean_user_content()` now **preserves all content inside wrapper tags** (`USER_REQUEST`, `ADDITIONAL_METADATA`, etc.) instead of stripping them — no information is discarded
- Error/unknown step content is no longer truncated at 500 chars — full content is preserved
- `format_conversation()` now accepts a `config=` parameter for one-call configuration
- `_format_tool_call()` respects `max_tool_output_length` for argument display
- `engine.py` passes full `config` object to `format_conversation` instead of individual flags

### Fixed
- **Idempotency fully resolved** — two consecutive runs now correctly produce `Written=0 Skipped=12` after a force rebuild (was intermittently re-writing 4–6 files on every run)
- Root cause: `last_viewed_at` was loaded inside `export_one` (only for changed notes) causing the stored hash to not match on the next run for those notes
- Set hash randomization (`PYTHONHASHSEED`) causing non-deterministic `code_languages` list ordering — fixed by sorting

---


The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.0.0] — 2026-07-09

### Added
- Complete package restructure into `sources/`, `analysis/`, `render/`, `sync/` subpackages
- `ConversationIntelligence` model: auto-extracts topics, technologies, files, commands, code languages
- `find_relations()` cross-links conversations using shared files, tech, topics, and commands
- Global vault index files: `Timeline.md`, `Conversations.md`, `Tags.md`, `Topics.md`
- Mermaid flowchart diagrams embedded in each conversation note
- Thinking-block support (`<details>` collapse for model reasoning)
- `--watch` mode with both polling and `watchdog`-based event watchers
- Proper `True/False/None` return sentinel from `export_one` for accurate stats
- `ExporterConfig` dataclass centralising all paths and settings
- 10-test unit-test suite runnable with `python run_tests.py`
- `pyproject.toml`, `requirements.txt`, `LICENSE`, `.gitignore`, `CONTRIBUTING.md`
- 70+ technology patterns in `wikilinks.py`

### Changed
- `pb_decoder.py` → `sources/pb_summaries.py`
- `transcript_reader.py` → `sources/transcript.py`
- `sqlite_fallback.py` → `sources/sqlite_db.py`
- `md_formatter.py` → `render/conversation.py`
- `wikilink_extractor.py` → `analysis/wikilinks.py`
- `exporter.py` → `sync/engine.py`
- `watcher.py` → `sync/watcher.py`
- Stats now correctly report `written` / `skipped` / `failed` separately
- YAML frontmatter expanded: `last_viewed`, `aliases`, `conversation_id`
- Tool results now rendered in `<details>` collapsibles with truncation at 3 000 chars

### Fixed
- `UnicodeEncodeError` on Windows cp1252 console (stdout wrapped to UTF-8)
- `NameError: os not defined` in `analysis/intelligence.py`
- Import of `TOOL_RESULT_TYPES` was incorrectly referencing `models` instead of `sources/transcript`
- Dead stats-recalculation loop removed from `run_export`

---

## [1.0.0] — 2026-07-09

### Added
- Initial working prototype
- `pb_decoder.py`: pure-Python protobuf parser for title index
- `transcript_reader.py`: JSONL reader + XML wrapper stripper
- `sqlite_fallback.py`: raw varint protobuf decoder for SQLite BLOBs
- `md_formatter.py`: YAML frontmatter + turn grouping + tool call blocks
- `wikilink_extractor.py`: 60+ tech term patterns → `[[WikiLinks]]` + `#tags`
- `exporter.py`: orchestrator with SHA-256 hash idempotency
- `watcher.py`: polling or `watchdog`-based file watcher
- `__main__.py`: CLI with `--source`, `--vault`, `--watch`, `--force`, `--list`, `--conv`
- Exported all 12 conversations successfully with Exported=12, Failed=0
- Idempotency confirmed: second run yields Skipped=12
