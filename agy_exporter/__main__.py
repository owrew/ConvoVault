"""
__main__.py
===========
CLI entrypoint for the production-grade Antigravity Obsidian Exporter.
"""
from __future__ import annotations
import argparse
import logging
import os
import sys
from pathlib import Path

from .config import ExporterConfig
from .sync.engine import run_export, export_one, load_transcript_for_id
from .sources.pb_summaries import parse_summaries
from .sync.state import ExportState
from .sync.watcher import start_watch

def _detect_source() -> str:
    candidates = [
        os.path.join(os.path.expanduser("~"), "OneDrive", "Downloads", "OBS"),
        os.path.join(os.path.expanduser("~"), "Downloads", "OBS"),
        os.getcwd(),
    ]
    for c in candidates:
        if (os.path.isdir(os.path.join(c, "conversations")) and
                os.path.isdir(os.path.join(c, "brain"))):
            return c
    return str(Path(__file__).parent.parent)

def _setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
    datefmt = "%H:%M:%S"
    
    # Force UTF-8 on Windows console output to prevent codepage character errors
    import io
    stdout = sys.stdout
    if hasattr(stdout, 'buffer'):
        stdout = io.TextIOWrapper(stdout.buffer, encoding='utf-8', errors='replace')
        
    logging.basicConfig(level=level, format=fmt, datefmt=datefmt,
                        handlers=[logging.StreamHandler(stdout)])
    logging.getLogger("urllib3").setLevel(logging.WARNING)

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agy_exporter",
        description="Sync Google Antigravity conversations to an Obsidian vault with index catalogs.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--source", "-s", default=None, help="Workspace source root containing brain/ and conversations/")
    p.add_argument("--vault", "-v", default=None, help="Obsidian vault target folder path")
    p.add_argument("--watch", "-w", action="store_true", help="Sync continuously in real-time")
    p.add_argument("--interval", type=float, default=5.0, help="Watch polling interval (seconds)")
    p.add_argument("--force", "-f", action="store_true", help="Force rebuild all notes ignoring mtime/hash changes")
    p.add_argument("--debug", "-d", action="store_true", help="Dump error details to .agy_debug/ on failure")
    p.add_argument("--conv", "-c", nargs="+", default=None, help="Filter to export specific conversation IDs")
    p.add_argument("--no-tool-results", action="store_true", help="Exclude tool result files and terminal outputs")
    p.add_argument("--max-tool-results-per-turn", type=int, default=None, help="Maximum number of tool result blocks per turn (default: unlimited)")
    p.add_argument("--max-tool-output-length", type=int, default=None, help="Maximum character length for each tool output block (default: unlimited)")
    p.add_argument("--verbose", "-V", action="store_true", help="Show verbose logs")
    p.add_argument("--list", action="store_true", help="Print conversation catalog with steps and titles")
    return p

def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    _setup_logging(args.verbose)
    log = logging.getLogger("agy_exporter.main")

    source_dir = args.source or _detect_source()
    vault_dir = args.vault or source_dir

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
        verbose=args.verbose
    )

    if not os.path.isdir(config.source_dir):
        log.error("Source folder not found: %s", config.source_dir)
        sys.exit(1)

    if args.list:
        _list_conversations(config)
        return

    if config.watch:
        # Watch Mode
        state = ExportState(config.vault_dir)
        meta_index = parse_summaries(config.summaries_pb_path)

        def re_export_callback(conv_id: str):
            ts = load_transcript_for_id(conv_id, config)
            if not ts or not ts.steps:
                return
            export_one(
                conv_id=conv_id,
                transcript=ts,
                config=config,
                meta_index=meta_index,
                state=state,
                all_meta=meta_index
            )
            state.save()

        def re_load_pb_callback():
            nonlocal meta_index
            meta_index = parse_summaries(config.summaries_pb_path)
            # Re-export all
            run_export(config)

        # Do initial pass
        run_export(config)
        
        log.info("Entering active watch loop...")
        start_watch(
            source_dir=config.source_dir,
            vault_dir=config.vault_dir,
            on_change=re_export_callback,
            on_pb_change=re_load_pb_callback,
            interval=config.watch_interval
        )
    else:
        # One-shot export
        stats = run_export(config)
        log.info(
            "Done — Written: %d  Skipped: %d  Failed: %d  Total: %d",
            stats.get('written', 0), stats.get('skipped', 0),
            stats.get('failed', 0), stats.get('total', 0)
        )

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
