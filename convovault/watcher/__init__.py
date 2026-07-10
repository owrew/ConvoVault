"""
watcher
=======
File system watcher to track continuous updates (via watchdog or polling).
"""
from .watcher import start_watch, PollingWatcher
