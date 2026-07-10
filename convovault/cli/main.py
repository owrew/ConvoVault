"""
main.py
=======
CLI entrypoint for ConvoVault with subcommand orchestration.
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import sys
from pathlib import Path

from typing import Dict, List, Optional
from ..config.exporter import ExporterConfig
from ..exporter.engine import run_export, export_one
from ..providers.plugin_loader import get_provider, list_providers
from ..state.state import ExportState
from ..watcher.watcher import start_watch

# ── Config file path ─────────────────────────────────────────────────────────

def _config_file_path() -> str:
    if os.name == 'nt':
        base = os.environ.get('APPDATA', os.path.expanduser('~'))
        return os.path.join(base, 'convovault', 'config.json')
    return os.path.expanduser('~/.config/convovault/config.json')

def _load_saved_config() -> dict:
    path = _config_file_path()
    if os.path.isfile(path):
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                return json.load(fh)
        except Exception:
            pass
    return {}

def _save_config(data: dict):
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

def _is_valid_source(path: str) -> bool:
    return os.path.isdir(os.path.join(path, "brain")) and (
        os.path.isdir(os.path.join(path, "conversations")) or
        os.path.isfile(os.path.join(path, "agyhub_summaries_proto.pb"))
    )

def _detect_source() -> str:
    candidates = [
        os.getcwd(),
        os.path.join(os.path.expanduser("~"), "OneDrive", "Downloads", "OBS"),
        os.path.join(os.path.expanduser("~"), "OneDrive", "Documents", "OBS"),
        os.path.join(os.path.expanduser("~"), "Downloads", "OBS"),
        os.path.join(os.path.expanduser("~"), "Documents", "OBS"),
        os.path.join(os.path.expanduser("~"), "Desktop", "OBS"),
        os.path.join(os.path.expanduser("~"), "OneDrive", "Downloads"),
        os.path.join(os.path.expanduser("~"), "Downloads"),
        os.path.join(os.path.expanduser("~"), "Documents"),
        os.path.expanduser("~/Library/Application Support/Antigravity"),
        os.path.expanduser("~/.antigravity"),
        os.path.expanduser("~/.config/antigravity"),
        os.path.expanduser("~/.local/share/antigravity"),
        os.path.expanduser("~/antigravity"),
    ]
    for c in candidates:
        if _is_valid_source(c):
            return c
    return os.getcwd()

def _resolve_paths(args) -> tuple[str, str, str]:
    saved = _load_saved_config()
    provider = args.provider or os.environ.get("AGY_PROVIDER") or saved.get("provider") or "antigravity"
    
    source_dir = (
        args.source
        or os.environ.get("AGY_SOURCE")
        or saved.get("source")
        or _detect_source()
    )
    
    vault_dir = (
        args.vault
        or os.environ.get("AGY_VAULT")
        or saved.get("vault")
        or source_dir
    )
    return provider, source_dir, vault_dir

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

# ── Commands ──────────────────────────────────────────────────────────────────

def handle_export(args):
    provider, source, vault = _resolve_paths(args)
    if args.save:
        _save_config({"provider": provider, "source": source, "vault": vault})
        
    config = ExporterConfig(
        source_dir=source,
        vault_dir=vault,
        provider=provider,
        force=args.force,
        debug=args.debug,
        conv_filter=args.conv,
        no_tool_results=args.no_tool_results,
        max_tool_results_per_turn=args.max_tool_results_per_turn,
        max_tool_output_length=args.max_tool_output_length,
        verbose=args.verbose,
    )
    
    if not os.path.isdir(config.source_dir) and not os.path.isfile(config.source_dir):
        print(f"[error] Source path not found: {config.source_dir}")
        sys.exit(1)
        
    print(f"Source   : {config.source_dir}")
    print(f"Vault    : {config.vault_dir}")
    print(f"Provider : {config.provider}")
    
    run_export(config)

def handle_watch(args):
    provider, source, vault = _resolve_paths(args)
    config = ExporterConfig(
        source_dir=source,
        vault_dir=vault,
        provider=provider,
        watch=True,
        watch_interval=args.interval,
        force=args.force,
        debug=args.debug,
        no_tool_results=args.no_tool_results,
        max_tool_results_per_turn=args.max_tool_results_per_turn,
        max_tool_output_length=args.max_tool_output_length,
        verbose=args.verbose,
    )
    
    print(f"Watching source: {config.source_dir} (interval: {config.watch_interval}s)")
    print(f"Syncing to vault: {config.vault_dir}")
    
    # Do initial run
    run_export(config)
    
    # Load state and provider summaries
    state = ExportState(config.vault_dir)
    prov = get_provider(config.provider)
    if not prov:
        print(f"[error] Provider '{config.provider}' not found.")
        sys.exit(1)
    meta_index = prov.load_metadata_index(config)

    def re_export_callback(conv_id: str):
        convo = prov.read_conversation(conv_id, config)
        if not convo or not convo.steps:
            return
        export_one(
            conv_id=conv_id, convo=convo,
            config=config, meta_index=meta_index,
            state=state, all_meta=meta_index,
        )
        state.save()

    def re_load_pb_callback():
        nonlocal meta_index
        meta_index = prov.load_metadata_index(config)
        run_export(config)

    start_watch(
        source_dir=config.source_dir,
        vault_dir=config.vault_dir,
        on_change=re_export_callback,
        on_pb_change=re_load_pb_callback,
        interval=config.watch_interval,
    )

def handle_providers(args):
    print("\n--- ConvoVault Registered Providers ---")
    for name in list_providers():
        print(f"  - {name}")
    print()

def handle_search(args):
    provider, source, vault = _resolve_paths(args)
    query = args.query.lower()
    print(f"Searching vault at {vault} for '{query}'...")
    chats_dir = os.path.join(vault, "AI Vault", "Chats")
    if not os.path.isdir(chats_dir):
        print("No exported notes directory found.")
        return
        
    matches = 0
    for fname in os.listdir(chats_dir):
        if not fname.endswith(".md"):
            continue
        path = os.path.join(chats_dir, fname)
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                content = fh.read()
            if query in content.lower():
                print(f"  [Match] [[{fname[:-3]}]]")
                matches += 1
        except Exception:
            pass
    print(f"\nFound {matches} matches total.")

def handle_stats(args):
    provider, source, vault = _resolve_paths(args)
    state = ExportState(vault)
    print("\n--- ConvoVault Sync Statistics ---")
    print(f"  Obsidian Vault  : {vault}")
    print(f"  Total Exported  : {len(state.state)} notes")
    print()

def handle_doctor(args):
    provider, source, vault = _resolve_paths(args)
    ok, bad = "[OK]", "[!!]"
    print("\n--- ConvoVault Doctor ---")
    print(f"  Active Provider: {provider}")
    print(f"  Source Path: {source} — {'Exists' if os.path.exists(source) else 'MISSING'}")
    print(f"  Vault Path:  {vault} — {'Exists' if os.path.exists(vault) else 'MISSING'}")
    
    prov_obj = get_provider(provider)
    if prov_obj:
        print(f"  Provider Resolve: {ok} resolved successfully")
    else:
        print(f"  Provider Resolve: {bad} FAILED to resolve '{provider}'")
        
    try:
        import sqlite3
        print(f"  sqlite3: {ok} module is available")
    except ImportError:
        print(f"  sqlite3: {bad} module missing")
        
    try:
        import watchdog
        print(f"  watchdog: {ok} observer available for active watching")
    except ImportError:
        print(f"  watchdog: [--] missing, using fallback polling watcher")
    print()

def handle_config(args):
    provider, source, vault = _resolve_paths(args)
    if args.action == "show":
        cfg_file = _config_file_path()
        saved = _load_saved_config()
        print("\n=== ConvoVault Active Configuration ===\n")
        print(f"  Config file : {cfg_file}")
        print(f"  Source dir  : {source}")
        print(f"  Vault dir   : {vault}")
        print(f"  Provider    : {provider}")
        print(f"  Saved file  : {saved or '(none)'}")
        print()
    elif args.action == "save":
        _save_config({"provider": provider, "source": source, "vault": vault})

def main(argv=None):
    p = argparse.ArgumentParser(prog="convovault", description="Universal AI Conversation Knowledge Vault.")
    subparsers = p.add_subparsers(dest="command", required=True)

    # Global options to share across subparsers
    gp = argparse.ArgumentParser(add_help=False)
    gp.add_argument("--source", "-s", help="Source folder path")
    gp.add_argument("--vault", "-v", help="Obsidian vault target folder path")
    gp.add_argument("--provider", "-p", help="AI provider name (e.g. 'antigravity', 'chatgpt')")
    gp.add_argument("--verbose", "-V", action="store_true", help="Enable verbose DEBUG logging")

    # export
    exp_p = subparsers.add_parser("export", parents=[gp], help="Export conversations to vault")
    exp_p.add_argument("--save", action="store_true", help="Save active paths to config file permanently")
    exp_p.add_argument("--force", "-f", action="store_true", help="Force rebuild all notes")
    exp_p.add_argument("--debug", "-d", action="store_true", help="Dump error details to .convovault_debug/")
    exp_p.add_argument("--conv", "-c", nargs="+", help="Export specific conversation UUID(s)")
    exp_p.add_argument("--no-tool-results", action="store_true", help="Omit tool result blocks")
    exp_p.add_argument("--max-tool-results-per-turn", type=int, help="Cap tool result blocks per turn")
    exp_p.add_argument("--max-tool-output-length", type=int, help="Cap characters per tool output block")

    # watch
    wat_p = subparsers.add_parser("watch", parents=[gp], help="Start continuous live sync")
    wat_p.add_argument("--interval", type=float, default=5.0, help="Watch polling interval (default: 5.0)")
    wat_p.add_argument("--force", "-f", action="store_true", help="Force rebuild all notes")
    wat_p.add_argument("--debug", "-d", action="store_true", help="Dump error details")
    wat_p.add_argument("--no-tool-results", action="store_true", help="Omit tool result blocks")
    wat_p.add_argument("--max-tool-results-per-turn", type=int, help="Cap tool result blocks")
    wat_p.add_argument("--max-tool-output-length", type=int, help="Cap characters")

    # providers
    subparsers.add_parser("providers", help="List registered providers")

    # search
    src_p = subparsers.add_parser("search", parents=[gp], help="Search exported Markdown notes")
    src_p.add_argument("query", help="Keyword search query")

    # stats
    subparsers.add_parser("stats", parents=[gp], help="Show synchronization statistics")

    # doctor
    subparsers.add_parser("doctor", parents=[gp], help="Run environment health diagnostics")

    # config
    cfg_p = subparsers.add_parser("config", parents=[gp], help="Configure persistent settings")
    cfg_p.add_argument("action", choices=["show", "save"], help="Config action to perform")

    # version
    subparsers.add_parser("version", help="Show version information")

    args = p.parse_args(argv)
    _setup_logging(args.verbose)

    if args.command == "export":
        handle_export(args)
    elif args.command == "watch":
        handle_watch(args)
    elif args.command == "providers":
        handle_providers(args)
    elif args.command == "search":
        handle_search(args)
    elif args.command == "stats":
        handle_stats(args)
    elif args.command == "doctor":
        handle_doctor(args)
    elif args.command == "config":
        handle_config(args)
    elif args.command == "version":
        from .. import __version__
        print(f"ConvoVault v{__version__}")

if __name__ == "__main__":
    main()
