# ConvoVault Studio 3.0

ConvoVault turns supported local AI transcripts and downloaded exports into linked Markdown notes and editable Obsidian Canvas maps. It works offline and uses no AI API keys.

## Open Studio on Windows

Double-click `release/ConvoVault-Studio.exe`, or `Start-Studio.cmd` in the complete release folder. The portable Windows executable includes Python and opens the interface in your default browser. The server listens only on this computer, on a randomly chosen port.

The executable is an unsigned local build. It was built and smoke-tested on this Windows 11 x64 machine; other Windows installations have not been tested.

The source version runs with Python 3.9 or newer:

```powershell
python -m convovault gui
```

For a separate native window, install the optional dependency and launch from source:

```powershell
python -m pip install '.[desktop]'
python -m convovault gui --native
```

The optional native-window installation has not been tested in this delivery. The portable executable uses the browser interface.

## Your first import

1. Choose **Connect a source**, or click a detected source in the left sidebar.
2. Select the assistant and its transcript folder or exported JSON/ZIP/database file. Source hints explain the supported format.
3. Choose your Obsidian vault. A new, separate folder also works; open it as a vault in Obsidian afterwards.
4. Choose a note mode and whether to create maps.
5. Click **Preview conversations**. Preview reads the source; it does not create vault files.
6. Review conversations and their matched classification phrases. Select the chats to include, then click **Export selected**. The select-all checkbox selects the current page of up to 100 conversations.
7. In Obsidian, open `AI Vault/Library.md`, `AI Vault/Brain.canvas`, or `AI Vault/Topics.canvas`.

Nothing is automatically imported merely because Studio detects an installed assistant. A detected folder means the location exists; preview determines whether its contents are readable.

## Note modes

| Mode | What it creates |
| --- | --- |
| Whole conversation | One complete Markdown note for each chat |
| Each exchange | A conversation index, plus one note per human prompt and the responses/tools that follow it |
| Every message | A conversation index, plus a note for every normalized user, assistant, system, or tool record |
| Whole chat + exchanges | Full conversation plus linked exchange notes |

An unfinished prompt remains as an exchange. Leading assistant/tool/context records form a leading part rather than being discarded. Consecutive assistant records stay with their user prompt. Tool-only Claude Code envelopes do not create human exchanges.

Each smaller note receives its own keyword classification. The whole-chat category can be manually overridden; this does not override the independently classified parts. Parts have links to their parent and their previous/next part.

Switching modes adds or updates the current output. Earlier output from other modes remains in the vault, and current indexes link to the chosen mode. ConvoVault does not delete old notes.

## Classification and search

The rules editor supports up to 50 categories, each with a name, color, and literal words or phrases. Separate phrases with commas. English and Arabic defaults are included; other languages can be added.

Matching uses Unicode word boundaries and counts distinct matching phrases. The highest count becomes the suggested category; ties use rule order. Unmatched chats go into **Unsorted**. This is an explainable keyword system, not semantic AI classification or a probability score.

Open a conversation in **Source preview** to change its category. The **Imported library** reflects the classifications stored in the exported notes. Re-export the source after changing rules or category overrides. Imported notes stay unchanged until then.

Library search checks the exported Markdown, including linked part notes, and requires every search word to appear. Source-preview search checks titles and the first prompt excerpt. Search stays on the device; there is no embedding server or third-party service.

## Maps and colors

The GUI's neural map displays the current page of conversations. Dots open conversations; connecting lines indicate a shared category or technology. The empty-state illustration is explicitly labeled as illustrative.

`Brain.canvas` uses a stylized two-hemisphere layout with readable note cards. `Topics.canvas` organizes note cards in category columns. They are normal JSON Canvas files: move cards, change colors, or edit groups in Obsidian. Topic and technology hub notes also connect the normal Obsidian graph.

The maps include at most 500 recently updated conversations to keep them manageable. The Markdown library contains all imported conversations. Colors and classifications reflect the most recent export of each conversation.

Obsidian's built-in graph supports color groups, but its normal force layout does not provide a fixed brain silhouette. Follow `AI Vault/Graph colors.md` to create matching graph groups. Existing `.obsidian` settings are not changed. See [Obsidian Graph view](https://obsidian.md/help/plugins/graph), [Canvas](https://obsidian.md/help/plugins/canvas), and [JSON Canvas](https://jsoncanvas.org/spec/1.0/).

Editing an exported Canvas is supported. A subsequent import preserves that edited file and creates an incoming generated copy. Open that new file to see the latest generated map.

## Background syncing

**Enable background sync** imports the entire currently configured source at the saved interval, with a minimum interval of 30 seconds. It is not restricted to the chats selected during a previous manual export. To restrict the source, point it at one transcript or a dedicated export folder.

Studio must stay running. Closing the browser tab does not stop its local server; reopening Studio starts another instance unless the earlier instance was closed. Use **Settings → Close Studio server** when finished. Sync starts paused when Studio is reopened and pauses automatically on import errors or unreadable records.

This is application-level background sync, not a Windows service, scheduled task, tray application, or start-at-login installation. ChatGPT/Claude web conversations update only after a new export is supplied.

## File safety and recovery

- Original transcripts and databases are read-only. Exports are kept in `AI Vault`, and root-level vault indexes are not overwritten.
- Provider-qualified identities and stable filename suffixes prevent cross-provider collisions. Chats without IDs get position-based identities within their export file; rearranging that file can change those identities.
- Unchanged generated files are skipped. If a generated note or map was edited, the edit remains and an incoming copy is created. Current library links follow the imported copy.
- New imports merge into the library. Importing another provider does not replace the previous provider's catalog.
- State lives in `AI Vault/.convovault/library.json`. The preceding manifest is saved as `library.previous.json` before each update. Keep both in your usual vault backups.
- An import lock prevents two ConvoVault processes writing the same vault at once. After a process crash, close that process before removing `AI Vault/.convovault/import.lock`.
- Import writes individual files atomically. It is not a filesystem-wide transaction: interrupted runs can leave generated files that a later run will preserve or re-index. No source file is removed during recovery.
- Version 2 notes and its old state remain in place. Version 3 uses its own manifest and provider subfolders; it does not automatically migrate or delete old exports.

Studio preferences, category overrides, and source/vault paths are saved in `%APPDATA%/convovault/studio.json` on Windows, or `~/.config/convovault/studio.json` elsewhere. Source chats are not stored there. CLI preferences use the separate existing `config.json`.

## Troubleshooting

**No conversations found:** check the assistant and source format. Some apps keep encrypted or proprietary account caches; these are not portable transcripts. Use an official export or the documented generic JSON format.

**Source and vault overlap:** choose separate folders. This prevents generated notes from being scanned as source conversations.

**An incomplete JSONL line is reported:** a running assistant may still be writing it. Complete records are imported; retry after the assistant finishes. In background mode, warnings pause sync so you can inspect them.

**The file picker does not open:** paste the complete path into the field. Linux Python builds may need their system Tk package for native folder dialogs.

**An old note is still visible after a mode change:** old notes are deliberately retained. Use `AI Vault/Library.md` for the current links.

**A note says image/media attachment:** original media files are not copied or decoded. Check the source assistant/export for those attachments.

**A cloud-only Codex task is missing:** the importer reads local rollout files. It does not query an OpenAI account or download cloud-only tasks.

## Later work

Optional local-model summaries and semantic classification are deferred. Other useful next steps are a system-tray controller, multiple saved sync profiles, richer attachment handling, and additional explicitly tested native app formats. These are not implemented in 3.0.

CLI defaults follow the selected provider. Set `CONVOVAULT_PROVIDER`, `CONVOVAULT_SOURCE`, and `CONVOVAULT_VAULT` to override defaults; the earlier `AGY_*` variables remain supported. An explicitly selected provider does not reuse a different provider's saved source folder.
