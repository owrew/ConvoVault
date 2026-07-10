"""
watcher.py
==========
Polished watcher running file monitors with minimal CPU footprint.
"""
from __future__ import annotations
import os
import time
import logging
from typing import Callable

log = logging.getLogger(__name__)

class PollingWatcher:
    def __init__(
        self,
        brain_dir: str,
        annot_dir: str,
        pb_path: str,
        on_change: Callable[[str], None],
        on_pb_change: Callable[[], None],
        interval: float = 5.0
    ):
        self.brain_dir = brain_dir
        self.annot_dir = annot_dir
        self.pb_path = pb_path
        self.on_change = on_change
        self.on_pb_change = on_pb_change
        self.interval = interval
        self._mtimes: dict[str, float] = {}
        self._pb_mtime: float = 0.0
        self._running = False

    def _scan(self) -> dict[str, float]:
        result = {}
        # Transcripts
        if os.path.isdir(self.brain_dir):
            for conv_id in os.listdir(self.brain_dir):
                base = os.path.join(self.brain_dir, conv_id, '.system_generated', 'logs')
                for f in ('transcript_full.jsonl', 'transcript.jsonl'):
                    p = os.path.join(base, f)
                    if os.path.isfile(p):
                        result[f"t:{conv_id}"] = os.path.getmtime(p)
                        break
        # Annotations
        if os.path.isdir(self.annot_dir):
            for fname in os.listdir(self.annot_dir):
                if fname.endswith('.pbtxt'):
                    conv_id = fname[:-6]
                    p = os.path.join(self.annot_dir, fname)
                    result[f"a:{conv_id}"] = os.path.getmtime(p)
        return result

    def start(self):
        log.info("Starting polling watcher (interval: %.1fs)", self.interval)
        self._running = True
        self._mtimes = self._scan()
        if os.path.isfile(self.pb_path):
            self._pb_mtime = os.path.getmtime(self.pb_path)

        try:
            while self._running:
                time.sleep(self.interval)
                
                # Check summaries pb
                if os.path.isfile(self.pb_path):
                    current_pb = os.path.getmtime(self.pb_path)
                    if current_pb != self._pb_mtime:
                        log.info("Summaries index updated: %s", self.pb_path)
                        self._pb_mtime = current_pb
                        self.on_pb_change()

                # Check transcripts/annotations
                current = self._scan()
                for k, mtime in current.items():
                    if k not in self._mtimes or self._mtimes[k] != mtime:
                        conv_id = k.split(":", 1)[1]
                        log.info("Change detected in %s (%s)", conv_id[:8], k.split(":", 1)[0])
                        self.on_change(conv_id)
                self._mtimes = current
        except KeyboardInterrupt:
            log.info("Watcher stopped by user")
        finally:
            self._running = False

    def stop(self):
        self._running = False

def start_watch(source_dir: str, vault_dir: str, on_change: Callable[[str], None], on_pb_change: Callable[[], None], interval: float = 5.0):
    brain_dir = os.path.join(source_dir, "brain")
    annot_dir = os.path.join(source_dir, "annotations")
    pb_path = os.path.join(source_dir, "agyhub_summaries_proto.pb")
    
    # Try using watchdog if installed
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class ExporterHandler(FileSystemEventHandler):
            def on_modified(self, event):
                if event.is_directory:
                    return
                path = os.path.abspath(event.src_path)
                
                # Check summaries pb
                if path == os.path.abspath(pb_path):
                    log.info("Watchdog: summaries index modified")
                    on_pb_change()
                    return
                
                # Check transcript
                if path.endswith(('transcript_full.jsonl', 'transcript.jsonl')):
                    parts = os.path.normpath(path).split(os.sep)
                    try:
                        idx = parts.index('.system_generated')
                        conv_id = parts[idx - 1]
                        log.info("Watchdog: transcript updated for %s", conv_id[:8])
                        on_change(conv_id)
                    except (ValueError, IndexError):
                        pass
                    return
                
                # Check annotations
                if path.endswith('.pbtxt') and os.sep + 'annotations' + os.sep in path:
                    fname = os.path.basename(path)
                    conv_id = fname[:-6]
                    log.info("Watchdog: annotations updated for %s", conv_id[:8])
                    on_change(conv_id)

            on_created = on_modified

        handler = ExporterHandler()
        observer = Observer()
        observer.schedule(handler, source_dir, recursive=True)
        observer.start()
        log.info("Watchdog file observer active for %s", source_dir)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
            observer.join()
            log.info("Watcher stopped by user")
    except ImportError:
        # Fall back to polling
        watcher = PollingWatcher(
            brain_dir=brain_dir,
            annot_dir=annot_dir,
            pb_path=pb_path,
            on_change=on_change,
            on_pb_change=on_pb_change,
            interval=interval
        )
        watcher.start()
