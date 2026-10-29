# 3.0.0 — 2026-10-29

- Added ConvoVault Studio with local source discovery, preview/selection, search, editable classification, and background sync.
- Added Codex local sessions and archives, Claude Code, Gemini CLI and portable JSON adapters.
- Fixed broken ChatGPT/Claude model construction, selected-branch handling, stale import caches and Open WebUI/legacy Ollama model construction.
- Added whole-chat, exchange and individual-message exports; bilingual keyword rules and manual whole-chat overrides.
- Added provider-separated note identities, merged catalogs, topic hubs, technology links and colored brain/topic Canvas maps.
- Preserved edited files with incoming copies and correct backlinks; added atomic writes, locking and previous-manifest recovery.
- Fixed the package build backend and CLI commands that lacked verbosity arguments; included GUI assets in the wheel and added a portable Windows launcher.
- Added 30 integration/regression tests; 45 combined tests pass locally.
- Local-model summaries, cloud-account downloads, proprietary app caches, tray/startup integration and semantic classification remain deferred.

---

# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.1.0] — 2026-07-10

### Added

**Archive-quality note rendering** (`render/conversation.py` rewrite)
- Every note now contains complete sections: Conversation Statistics, Technologies, Topics, Files Mentioned, Commands Executed, Wiki Links, Related Conversations, Timeline, and Conversation Intelligence footer
- Conversation Statistics table with per-tool call breakdown
- Tool result headers now show descriptive context (`VIEW_FILE → package.json`) instead of generic type names
- Full ISO timestamp display on every turn header (`2026-06-25 20:06 UTC`)
- `duration` field calculated and shown in metadata table and YAML frontmatter
- Extended YAML frontmatter: `duration`, `user_turns`, `assistant_turns`, `tool_calls_total`, `thinking_blocks`, `technologies`, `topics`, `code_languages`
- `_collect_stats()` helper for per-conversation statistics
- `_tool_result_title()` helper for descriptive tool result headers
- `_duration_str()` helper for human-readable conversation duration
- Timeline section (chronological event log, up to 50 entries)
- Files Mentioned and Commands Executed sections show ALL items (no truncation)

**Improved summary generation** (`analysis/intelligence.py`)
- Lists ALL user requests (numbered) instead of only the first
- Shows total tool call count + top-8 per-tool breakdown
- Tracks files written/edited separately from files read
- Tracks commands executed with preview
- Reports error messages encountered during the session

**System metadata stripping** (`sources/transcript.py`)
- `ADDITIONAL_METADATA`, `USER_SETTINGS_CHANGE`, `SYSTEM_REMINDERS`, `SYSTEM_MESSAGE` blocks now removed entirely (tag + content) — these are system-injected and have no place in exported notes
- `USER_REQUEST` wrapper tags stripped but inner content preserved
- Inner XML authored by the user (e.g. `<config>...</config>`) left untouched

**4-level configuration system** (`__main__.py` rewrite)
- Priority: CLI flags → `AGY_SOURCE`/`AGY_VAULT` env vars → config file → auto-detection
- `--save-config` — persist `--source` and `--vault` to `%APPDATA%\agy_exporter\config.json` permanently
- `--show-config` — print all resolved paths with `[OK]`/`[!!]` status and exit
- Auto-detection expanded from 2 to 12+ candidate paths (Windows, macOS, Linux)
- Startup always prints active Source and Vault paths

**Multi-AI source readers** (new files)
- `sources/chatgpt.py` — parses ChatGPT `conversations.json` exports (tree → linear steps)
- `sources/claude_ai.py` — parses Claude.ai exports, handles text + tool_use + tool_result blocks
- `sources/ollama.py` — reads Open WebUI SQLite (`webui.db`) and LM Studio JSON files

### Changed
- `clean_user_content()` behaviour reversed: now **strips** `ADDITIONAL_METADATA` content (was keeping it)
- README Quick Start expanded to 5 steps with configuration priority table, auto-detection path list, `--save-config` workflow, `--show-config` sample output
- README CLI Options table updated with `--save-config`, `--show-config`, `--max-tool-results-per-turn`, `--max-tool-output-length`
- README typing SVG enlarged: height 80 → 120px, width 600 → 700px, font-size 22 → 24pt

### Fixed
- **Idempotency** — annotations now loaded eagerly before any rendering so `last_viewed` is always populated, making consecutive runs produce `Written=0 Skipped=12`
- **Non-determinism** — `code_languages` sorted to prevent `PYTHONHASHSEED`-driven hash changes
- Windows console `UnicodeEncodeError` in `--show-config` output (removed emoji, use ASCII `[OK]`/`[!!]`)

### Tests
- 15 tests, 0 failures
- 4 new `test_transcript.py` cases covering metadata stripping, settings change stripping, inner XML preservation
- 4 new `test_markdown.py` cases covering metadata stripping, thinking blocks, required sections, new frontmatter

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
