# Migration Guide: agy_exporter → ConvoVault

> **Project renamed in v2.1.0** — The project has been rebranded and architecturally upgraded from `agy_exporter` to **ConvoVault**.

---

## What Changed

| Before | After |
|---|---|
| Package: `agy_exporter` | Package: `convovault` |
| CLI: `python -m agy_exporter` | CLI: `python -m convovault` or `convovault` |
| Single provider (Antigravity) | Multi-provider architecture |
| Flat module structure | Layered `providers/`, `rendering/`, `analysis/` architecture |
| State file: `.agy_export_state.json` | State file: `.convovault_state.json` (legacy migrated automatically) |
| Config: `%APPDATA%\agy_exporter\config.json` | Config: `%APPDATA%\convovault\config.json` |

---

## Backward Compatibility

- `python -m agy_exporter` still works via a thin wrapper that calls `convovault export`
- `agy-exporter` CLI entrypoint still works via the same wrapper
- The old state file `.agy_export_state.json` is automatically read and migrated to `.convovault_state.json` on first run
- All existing exported notes remain valid — no reformatting required

---

## New CLI Syntax

Old:
```bash
python -m agy_exporter --source PATH --vault PATH --watch
python -m agy_exporter --force --conv UUID
python -m agy_exporter --show-config
python -m agy_exporter --save-config
```

New (subcommand style):
```bash
convovault export --source PATH --vault PATH
convovault watch  --source PATH --vault PATH
convovault export --force --conv UUID
convovault config show
convovault config save --source PATH --vault PATH
convovault providers
convovault doctor
convovault stats
convovault version
```

---

## Config File Migration

**Old location:** `%APPDATA%\agy_exporter\config.json`
**New location:** `%APPDATA%\convovault\config.json`

Both files are separate. Re-run `--save-config` once to write the new location:

```bash
convovault config save --source "C:\path\to\source" --vault "C:\path\to\vault"
```

---

## Import Changes (for Python API users)

Old:
```python
from agy_exporter import ExporterConfig, run_export
from agy_exporter.models import ConversationTranscript, Step
from agy_exporter.render.conversation import format_conversation
from agy_exporter.analysis.intelligence import generate_intelligence
```

New:
```python
from convovault import ExporterConfig, run_export
from convovault.models import Conversation, Step
from convovault.rendering.conversation import format_conversation
from convovault.analysis.intelligence import generate_intelligence
```

The old `agy_exporter` imports remain working as aliases for backward compatibility.

---

## Provider Specification

By default, `convovault export` uses the `antigravity` provider — identical behavior to the old `agy_exporter`.

To explicitly specify a provider:

```bash
convovault export --provider antigravity --source PATH
convovault export --provider chatgpt --source conversations.json
convovault export --provider claude  --source conversations.json
convovault export --provider openwebui --source /path/to/webui.db
```

---

## No Data Loss

Your existing exported notes in Obsidian are not affected. The state file migration is automatic and backward-compatible. All Antigravity conversation data is read exactly as before.
