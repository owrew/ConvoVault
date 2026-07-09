"""
__main__.py
===========
CLI entrypoint for the Antigravity Obsidian Exporter.

Configuration priority (highest → lowest):
  1. CLI flags  --source / --vault
  2. Environment variables  AGY_SOURCE / AGY_VAULT
  3. Config file  ~/.agy_exporter.json  (or %APPDATA%\\agy_exporter.json on Windows)
  4. Auto-detection  (scans common Antigravity install paths)
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import sys
from pathlib import Path

from .config import ExporterConfig
from .sync.engine import run_export, export_one, load_transcript_for_id
from .sources.pb_summaries import parse_summaries
from .sync.state import ExportState
from .sync.watcher import start_watch

# ── Config file path ─────────────────────────────────────────────────────────

def _config_file_path() -> str:
    """Return path to the persistent JSON config file."""
    if os.name == 'nt':
        # Windows: %APPDATA%\agy_exporter\config.json
        base = os.environ.get('APPDATA', os.path.expanduser('~'))
        return os.path.join(base, 'agy_exporter', 'config.json')
    # macOS / Linux: ~/.config/agy_exporter/config.json
    return os.path.expanduser('~/.config/agy_exporter/config.json')

def _load_saved_config() -> dict:
    """Load persisted source/vault paths from the config file."""
    path = _config_file_path()
    if os.path.isfile(path):
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                return json.load(fh)
        except Exception:
            pass
    return {}

def _save_config(data: dict):
    """Persist source/vault paths to the config file."""
    path = _config_file_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        existing = _load_saved_config()
        existing.update(data)
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(existing, fh, indent=2)
        print(f"[config] Saved to {path}")
    except Exception as e:
        print(f"[config] Warning: could not save config — {e}")

# ── Source auto-detection ─────────────────────────────────────────────────────

_ANTIGRAVITY_MARKERS = ("brain", "conversations", "agyhub_summaries_proto.pb")

def _is_valid_source(path: str) -> bool:
    """Return True if path looks like an Antigravity workspace root."""
    return os.path.isdir(os.path.join(path, "brain")) and (
        os.path.isdir(os.path.join(path, "conversations")) or
        os.path.isfile(os.path.join(path, "agyhub_summaries_proto.pb"))
    )

def _detect_source() -> str:
    """
    Scan common install locations for the Antigravity workspace.
    Checks in order:
      1. Current working directory
      2. Common Windows paths (OneDrive, Downloads, Documents, AppData)
      3. Common macOS / Linux paths
    """
    candidates = [
        # 1. CWD first
        os.getcwd(),

        # 2. Windows — common locations
        os.path.join(os.path.expanduser("~"), "OneDrive", "Downloads", "OBS"),
        os.path.join(os.path.expanduser("~"), "OneDrive", "Documents", "OBS"),
        os.path.join(os.path.expanduser("~"), "Downloads", "OBS"),
        os.path.join(os.path.expanduser("~"), "Documents", "OBS"),
        os.path.join(os.path.expanduser("~"), "Desktop", "OBS"),

        # 3. Windows — Antigravity may sit directly in Downloads / Documents
        os.path.join(os.path.expanduser("~"), "OneDrive", "Downloads"),
        os.path.join(os.path.expanduser("~"), "Downloads"),
        os.path.join(os.path.expanduser("~"), "Documents"),

        # 4. macOS / Linux
        os.path.expanduser("~/Library/Application Support/Antigravity"),
        os.path.expanduser("~/.antigravity"),
        os.path.expanduser("~/.config/antigravity"),
        os.path.expanduser("~/.local/share/antigravity"),
        os.path.expanduser("~/antigravity"),
    ]

    for c in candidates:
        if _is_valid_source(c):
            return c

    # Last resort: script's parent directory
    return str(Path(__file__).parent.parent)

# ── Logging setup ─────────────────────────────────────────────────────────────

def _setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
    datefmt = "%H:%M:%S"
    import io
    stdout = sys.stdout
    if hasattr(stdout, 'buffer'):
        stdout = io.TextIOWrapper(stdout.buffer, encoding='utf-8', errors='replace')
    logging.basicConfig(level=level, format=fmt, datefmt=datefmt,
                        handlers=[logging.StreamHandler(stdout)])
    logging.getLogger("urllib3").setLevel(logging.WARNING)

# ── Argument parser ───────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agy_exporter",
        description=(
            "Sync Google Antigravity conversations to an Obsidian vault.\n\n"
            "Configuration is read from (highest priority first):\n"
            "  1. CLI flags\n"
            "  2. Environment variables  AGY_SOURCE  AGY_VAULT\n"
            f"  3. Config file           {_config_file_path()}\n"
            "  4. Auto-detection        (scans common Antigravity paths)\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--source", "-s", default=None,
                   help="Antigravity workspace root folder (contains brain/ and conversations/)")
    p.add_argument("--vault", "-v", default=None,
                   help="Obsidian vault root folder (notes written to vault/AI Vault/Chats/)")
    p.add_argument("--save-config", action="store_true",
                   help="Save --source and --vault to config file so you never need to type them again")
    p.add_argument("--show-config", action="store_true",
                   help="Print the current resolved configuration and exit")
    p.add_argument("--watch", "-w", action="store_true",
                   help="Sync continuously — re-exports any conversation the moment it changes")
    p.add_argument("--interval", type=float, default=5.0,
                   help="Watch polling interval in seconds (default: 5.0)")
    p.add_argument("--force", "-f", action="store_true",
                   help="Force rebuild all notes ignoring hash/mtime cache")
    p.add_argument("--debug", "-d", action="store_true",
                   help="Write decode errors to .agy_debug/ subdirectory")
    p.add_argument("--conv", "-c", nargs="+", default=None,
                   help="Export only specific conversation UUIDs")
    p.add_argument("--no-tool-results", action="store_true",
                   help="Omit tool output blocks (produces shorter notes)")
    p.add_argument("--max-tool-results-per-turn", type=int, default=None,
                   help="Max tool result blocks per assistant turn (default: unlimited)")
    p.add_argument("--max-tool-output-length", type=int, default=None,
                   help="Max characters per tool output block (default: unlimited)")
    p.add_argument("--verbose", "-V", action="store_true",
                   help="Enable DEBUG-level logging")
    p.add_argument("--list", action="store_true",
                   help="Print conversation catalog and exit")
    return p

# ── Main ──────────────────────────────────────────────────────────────────────

def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    _setup_logging(args.verbose)
    log = logging.getLogger("agy_exporter.main")

    # ── Resolve source and vault (4-level priority) ───────────────────────────
    saved = _load_saved_config()

    source_dir = (
        args.source                          # 1. CLI flag
        or os.environ.get("AGY_SOURCE")      # 2. Environment variable
        or saved.get("source")               # 3. Saved config file
        or _detect_source()                  # 4. Auto-detection
    )

    vault_dir = (
        args.vault                           # 1. CLI flag
        or os.environ.get("AGY_VAULT")       # 2. Environment variable
        or saved.get("vault")                # 3. Saved config file
        or source_dir                        # 4. Default: same as source
    )

    # ── Save config if requested ──────────────────────────────────────────────
    if args.save_config:
        _save_config({"source": source_dir, "vault": vault_dir})

    config = ExporterConfig(
        source_dir=source_dir,
        vault_dir=vault_dir,
        watch=args.watch,
        watch_interval=args.interval,
        force=args.force,
        debug=args.debug,
        conv_filter=args.conv,
        no_tool_results=args.no_tool_results,
        max_tool_results_per_turn=args.max_tool_results_per_turn,
        max_tool_output_length=args.max_tool_output_length,
        verbose=args.verbose,
    )

    # ── Show config ───────────────────────────────────────────────────────────
    if args.show_config:
        _print_config(config)
        return

    if not os.path.isdir(config.source_dir):
        log.error("Source folder not found: %s", config.source_dir)
        log.error("Use --source to specify your Antigravity workspace folder.")
        sys.exit(1)

    log.info("Source : %s", config.source_dir)
    log.info("Vault  : %s", config.vault_dir)

    if args.list:
        _list_conversations(config)
        return

    if config.watch:
        state = ExportState(config.vault_dir)
        meta_index = parse_summaries(config.summaries_pb_path)

        def re_export_callback(conv_id: str):
            ts = load_transcript_for_id(conv_id, config)
            if not ts or not ts.steps:
                return
            export_one(
                conv_id=conv_id, transcript=ts,
                config=config, meta_index=meta_index,
                state=state, all_meta=meta_index,
            )
            state.save()

        def re_load_pb_callback():
            nonlocal meta_index
            meta_index = parse_summaries(config.summaries_pb_path)
            run_export(config)

        run_export(config)
        log.info("Entering active watch loop…")
        start_watch(
            source_dir=config.source_dir,
            vault_dir=config.vault_dir,
            on_change=re_export_callback,
            on_pb_change=re_load_pb_callback,
            interval=config.watch_interval,
        )
    else:
        stats = run_export(config)
        log.info(
            "Done — Written: %d  Skipped: %d  Failed: %d  Total: %d",
            stats.get('written', 0), stats.get('skipped', 0),
            stats.get('failed', 0), stats.get('total', 0),
        )

def _print_config(config: ExporterConfig):
    """Print resolved configuration for debugging."""
    cfg_file = _config_file_path()
    saved = _load_saved_config()
    ok  = "[OK]"
    bad = "[!!]"
    warn = "[--]"
    print("\n=== Antigravity Obsidian Exporter - Active Configuration ===\n")
    print(f"  Config file : {cfg_file}")
    print(f"  Source dir  : {config.source_dir}")
    print(f"    brain/    : {ok  if os.path.isdir(config.brain_dir)            else bad } {'found' if os.path.isdir(config.brain_dir) else 'NOT FOUND'}")
    print(f"    convo/    : {ok  if os.path.isdir(config.conversations_dir)    else warn} {'found' if os.path.isdir(config.conversations_dir) else 'not found'}")
    print(f"    summ.pb   : {ok  if os.path.isfile(config.summaries_pb_path)   else warn} {'found' if os.path.isfile(config.summaries_pb_path) else 'not found'}")
    print(f"  Vault dir   : {config.vault_dir}")
    print(f"  Output dir  : {config.output_chats_dir}")
    print(f"  Saved cfg   : {saved or '(none)'}")
    print(f"\n  Env AGY_SOURCE : {os.environ.get('AGY_SOURCE', '(not set)')}")
    print(f"  Env AGY_VAULT  : {os.environ.get('AGY_VAULT',  '(not set)')}")
    print()

def _list_conversations(config: ExporterConfig):
    from .sync.engine import discover_conversations
    meta_index = parse_summaries(config.summaries_pb_path)
    conv_ids = discover_conversations(config)
    print(f"\n{'Conv ID':<38}  {'Steps':>6}  Title")
    print('-' * 90)
    for cid in conv_ids:
        meta = meta_index.get(cid)
        title = meta.title if meta else cid[:8]
        steps = meta.step_count if meta else 0
        print(f"{cid}  {steps:>6}  {title[:45]}")
    print(f"\n{len(conv_ids)} conversations total")

if __name__ == "__main__":
    main()
