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
from ..config.exporter import ExporterConfig
from ..exporter.engine import run_export
from ..providers.plugin_loader import get_provider, list_providers

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


def _detect_source(provider="antigravity") -> str:
    if provider != "antigravity":
        from ..discovery import discover_sources
        candidates = [source for source in discover_sources() if source["provider"] == provider]
        found = next((source for source in candidates if source["exists"]), None)
        if found:
            return found["path"]
        if candidates:
            return candidates[0]["path"]
        return os.getcwd()  # Portable exports can be supplied in the current folder.
    candidates = [
        os.getcwd(),
        os.path.join(os.path.expanduser("~"), ".gemini", "antigravity"),  # Default install path
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
    provider = args.provider or os.environ.get("CONVOVAULT_PROVIDER") or os.environ.get("AGY_PROVIDER") or saved.get("provider") or "antigravity"

    source_dir = (
        args.source
        or os.environ.get("CONVOVAULT_SOURCE")
        or os.environ.get("AGY_SOURCE")
        or (saved.get("source") if saved.get("provider", "antigravity") == provider else None)
        or _detect_source(provider)
    )

    vault_dir = (
        args.vault
        or os.environ.get("CONVOVAULT_VAULT")
        or os.environ.get("AGY_VAULT")
        or saved.get("vault")
        or os.path.expanduser("~/Documents/ConvoVault")
    )
    return provider, source_dir, vault_dir


def _setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
    datefmt = "%H:%M:%S"
    stdout = sys.stdout
    if hasattr(stdout, 'reconfigure'):
        stdout.reconfigure(encoding='utf-8', errors='replace')
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
        note_mode=args.note_mode,
        create_maps=not args.no_maps,
        classification_rules=_read_rules(args.rules),
    )

    if not os.path.isdir(config.source_dir) and not os.path.isfile(config.source_dir):
        print(f"[error] Source path not found: {config.source_dir}")
        sys.exit(1)

    print(f"Source   : {config.source_dir}")
    print(f"Vault    : {config.vault_dir}")
    print(f"Provider : {config.provider}")

    stats = run_export(config)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    if stats['failed'] or not stats['total']:
        raise SystemExit(1)


def handle_watch(args):
    import time
    provider, source, vault = _resolve_paths(args)
    config = ExporterConfig(source_dir=source, vault_dir=vault, provider=provider,
                            note_mode=args.note_mode, create_maps=not args.no_maps,
                            classification_rules=_read_rules(args.rules),
                            no_tool_results=args.no_tool_results,
                            max_tool_results_per_turn=args.max_tool_results_per_turn,
                            max_tool_output_length=args.max_tool_output_length)
    print(f"Watching {source}. Press Ctrl+C to stop.")
    try:
        while True:
            print(json.dumps(run_export(config), ensure_ascii=False))
            time.sleep(max(5, args.interval))
    except KeyboardInterrupt:
        return


def handle_providers(args):
    print("\n--- ConvoVault Registered Providers ---")
    for name in list_providers():
        print(f"  - {name}")
    print()


def handle_search(args):
    from ..workspace import search_library
    _, _, vault = _resolve_paths(args)
    for entry in search_library(vault, args.query):
        print(f"{entry['provider']}: {entry['title']}\n  {os.path.join(vault, entry['path'])}")


def handle_stats(args):
    from ..workspace import load_library
    _, _, vault = _resolve_paths(args)
    library = load_library(vault)
    print(json.dumps({'vault': vault, 'conversations': len(library['conversations']),
                      'managed_files': len(library['artifacts'])}, indent=2))


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
        import sqlite3  # noqa: F401
        print(f"  sqlite3: {ok} module is available")
    except ImportError:
        print(f"  sqlite3: {bad} module missing")

    try:
        import watchdog  # noqa: F401
        print(f"  watchdog: {ok} observer available for active watching")
    except ImportError:
        print("  watchdog: [--] missing, using fallback polling watcher")
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


def _read_rules(path):
    if not path:
        return None
    from ..analysis.classification import validate_rules
    with open(path, encoding="utf-8-sig") as fh:
        return validate_rules(json.load(fh))


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
    exp_p.add_argument("--note-mode", choices=["conversation", "exchanges", "messages", "both"], default="conversation")
    exp_p.add_argument("--no-maps", action="store_true", help="Do not generate Canvas maps")
    exp_p.add_argument("--rules", help="Classification rules JSON file")

    # watch
    wat_p = subparsers.add_parser("watch", parents=[gp], help="Start continuous live sync")
    wat_p.add_argument("--interval", type=float, default=5.0, help="Watch polling interval (default: 5.0)")
    wat_p.add_argument("--force", "-f", action="store_true", help="Force rebuild all notes")
    wat_p.add_argument("--debug", "-d", action="store_true", help="Dump error details")
    wat_p.add_argument("--no-tool-results", action="store_true", help="Omit tool result blocks")
    wat_p.add_argument("--max-tool-results-per-turn", type=int, help="Cap tool result blocks")
    wat_p.add_argument("--max-tool-output-length", type=int, help="Cap characters")
    wat_p.add_argument("--note-mode", choices=["conversation", "exchanges", "messages", "both"], default="conversation")
    wat_p.add_argument("--no-maps", action="store_true")
    wat_p.add_argument("--rules", help="Classification rules JSON file")

    gui_p = subparsers.add_parser("gui", help="Open ConvoVault Studio")
    gui_p.add_argument("--native", action="store_true")
    gui_p.add_argument("--no-browser", action="store_true")
    gui_p.add_argument("--port", type=int, default=0)
    subparsers.add_parser("discover", help="List common local transcript paths and availability")
    preview_p = subparsers.add_parser("preview", parents=[gp], help="Read and classify without writing notes")
    preview_p.add_argument("--rules", help="Classification rules JSON file")

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
    _setup_logging(getattr(args, 'verbose', False))

    if args.command == "gui":
        from ..gui.server import main as gui_main
        options = ["--port", str(args.port)]
        if args.native:
            options.append("--native")
        if args.no_browser:
            options.append("--no-browser")
        gui_main(options)
    elif args.command == "discover":
        from ..discovery import discover_sources, EXPORT_SOURCES
        print(json.dumps({'local': discover_sources(), 'exports': EXPORT_SOURCES}, ensure_ascii=False, indent=2))
    elif args.command == "preview":
        from ..workspace import load_conversations, describe
        provider, source, vault = _resolve_paths(args)
        rules = _read_rules(args.rules)
        conversations, warnings = load_conversations(ExporterConfig(source, vault, provider))
        print(json.dumps({'conversations': [describe(c, rules) for c in conversations], 'warnings': warnings}, ensure_ascii=False, indent=2))
    elif args.command == "export":
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
