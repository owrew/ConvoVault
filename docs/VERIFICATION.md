# Local verification — 29 October 2026

## Automated checks

`python run_tests.py` runs the original 15 regression functions and 30 new integration/regression tests: **45 tests passed**.

New checks cover ChatGPT branch choice and malformed cycles, ZIP import without extraction, Claude tools, Claude Code tool envelopes, Gemini CLI JSON, duplicate-free and mixed-stream Codex messages, archived sessions, Codex title indexes, source-cache refresh, ID collisions, Arabic rules, overrides, all split modes, full-text search of split notes, preserved edited notes and valid bidirectional links, multi-provider catalogs, unchanged-file skipping, restoration of missing notes, Canvas references, source/output separation, damaged-manifest handling, read-only SQLite, authenticated GUI API access, cross-origin rejection, preview/export, and the background scheduler's error pause.

Python compilation, JavaScript syntax, the repository's lint configuration, and wheel packaging are checked separately. The installed wheel includes the GUI assets.

## Real-source boundary

A real local Codex rollout was imported into a separate temporary vault:

- 1 conversation with **132 normalized records** and **59 tool calls**.
- 17 generated files, no import warnings.
- The source transcript's SHA-256 was identical before and after.
- The temporary vault was removed after verification; its private content is not in the release package.

This verifies that observed local Codex data works. It does not prove compatibility with every past/future Codex version or cloud-only task.

## Interface and packaging

The browser interface is checked with the synthetic sample data: source preview, selecting and exporting chats, full-text search, conversation inspection, classification editing, rules, sync controls and the map. A screenshot in `docs/images/studio.png` shows synthetic example conversations, not the user's private chats.

The Windows executable and installed wheel are tested as separate launch paths. Their final smoke-test results are recorded in `release/verification.json` in the delivered folder. The executable was built locally for Windows x64; it is unsigned. The optional pywebview native window and other operating systems were not exercised here.

Canvas JSON was validated for unique node IDs and references to real exported notes. Obsidian's installed application was not used for the automated checks, so no claim is made that every theme/plugin combination was tested.

## Remaining limits

Classification is local keyword matching with evidence, not model-based semantic understanding. Source-preview search checks titles/excerpts; imported-library search checks Markdown content. Background sync runs only while Studio is running and targets one configured source. The GUI shows 100 results per page; generated maps show up to 500 recent conversations. Large JSON exports are held in memory. Attachments, proprietary desktop caches, cloud downloads and local-model summaries remain outside the implemented scope.
