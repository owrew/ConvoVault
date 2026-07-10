"""
__main__.py
===========
Backward-compatible wrapper redirecting agy_exporter to convovault.
"""
from __future__ import annotations
import sys
import logging
from convovault.cli.main import main as cv_main

log = logging.getLogger("agy_exporter.legacy")

def main():
    print("[migration] Warning: 'agy_exporter' is deprecated. Please use 'convovault' instead.")
    
    # Translate old CLI arguments to convovault subcommands
    args = sys.argv[1:]
    
    # Determine the subcommand
    if "--watch" in args or "-w" in args:
        cmd = ["watch"]
        # Remove --watch/-w from translated args as it is implicit in the subcommand
        cmd_args = [a for a in args if a not in ("--watch", "-w")]
    elif "--list" in args:
        # Use export with --list which maps to listing in the legacy logic,
        # or call cv_main directly with providers/custom
        cmd = ["export"]
        cmd_args = args
    else:
        cmd = ["export"]
        cmd_args = args

    # Reconstruct sys.argv for convovault main
    cv_argv = [sys.argv[0]] + cmd + cmd_args
    cv_main(cv_argv[1:])

if __name__ == "__main__":
    main()
