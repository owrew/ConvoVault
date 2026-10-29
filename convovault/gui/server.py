"""Loopback-only GUI with authenticated API, background jobs and read-only previews."""
from __future__ import annotations

import argparse
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, urlparse
import webbrowser

from ..analysis.classification import DEFAULT_RULES, validate_rules
from ..config.exporter import ExporterConfig
from ..discovery import discover_sources, EXPORT_SOURCES
from ..workspace import atomic_text, describe, export_library, load_conversations, render_steps, search_library, safe_relative

STATIC = Path(__file__).parent / "static"


def settings_file():
    base = Path(os.environ.get("APPDATA", Path.home() / ".config"))
    return base / "convovault" / "studio.json"


def default_settings():
    return {"provider": "codex", "source": str(Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))),
            "vault": str(Path.home() / "Documents" / "ConvoVault"), "note_mode": "both", "create_maps": True,
            "rules": copy.deepcopy(DEFAULT_RULES), "overrides": {}, "sync_interval": 60}


class Studio:
    def __init__(self, settings_path=None):
        self.settings_path = Path(settings_path) if settings_path else settings_file()
        self.settings = default_settings()
        if self.settings_path.exists():
            try:
                self.settings.update(json.loads(self.settings_path.read_text(encoding="utf-8")))
                validate_rules(self.settings["rules"])
            except (ValueError, OSError):
                self.settings = default_settings()
        self.lock = threading.RLock()
        self.preview = []
        self.preview_source = None
        self.job = {"busy": False, "kind": "", "error": "", "result": None}
        self.sync = False
        self.next_sync = 0
        self.stop = threading.Event()
        threading.Thread(target=self._scheduler, daemon=True).start()

    def config(self, values=None):
        data = {**self.settings, **(values or {})}
        if not data.get("source", "").strip() or not data.get("vault", "").strip():
            raise ValueError("Choose a source and an Obsidian vault folder")
        return ExporterConfig(source_dir=data["source"], vault_dir=data["vault"], provider=data["provider"],
                              note_mode=data["note_mode"], create_maps=bool(data["create_maps"]),
                              classification_rules=validate_rules(data["rules"]), category_overrides=data["overrides"])

    def save(self, values):
        allowed = set(default_settings())
        if not isinstance(values, dict) or set(values) - allowed:
            raise ValueError("Unknown settings")
        with self.lock:
            if self.job["busy"]:
                raise ValueError("Wait for the current job before changing settings")
            proposed = {**self.settings, **values}
            if not isinstance(proposed["overrides"], dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in proposed["overrides"].items()):
                raise ValueError("Invalid category overrides")
            proposed["sync_interval"] = max(30, min(86400, int(proposed["sync_interval"])))
            self.config(proposed)
            atomic_text(self.settings_path, json.dumps(proposed, ensure_ascii=False, indent=2))
            self.settings = proposed

    def start_job(self, kind, selected=None):
        with self.lock:
            if self.job["busy"]:
                raise ValueError("Another job is running")
            config = self.config()
            if selected is not None:
                if not isinstance(selected, list) or any(not isinstance(k, str) for k in selected) or not selected:
                    raise ValueError("Select at least one conversation")
                config.conv_filter = selected
            job_id = str(time.time_ns())
            self.job = {"id": job_id, "busy": True, "kind": kind, "error": "", "result": None}

        def work():
            result, error = None, ""
            try:
                if kind == "preview":
                    conversations, warnings = load_conversations(config)
                    with self.lock:
                        self.preview = conversations
                        self.preview_source = (config.provider, config.source_dir)
                    result = {"total": len(conversations), "warnings": warnings}
                elif kind == "export":
                    result = export_library(config)
                else:
                    raise ValueError("Unknown job")
            except Exception as exc:
                error = str(exc)
            finally:
                with self.lock:
                    self.job = {"id": job_id, "busy": False, "kind": kind, "error": error, "result": result}
                    self.next_sync = time.time() + self.settings["sync_interval"]
                    if error or (kind == "export" and result and (result.get("failed") or not result.get("total"))):
                        self.sync = False
        threading.Thread(target=work, daemon=True).start()

    def _scheduler(self):
        while not self.stop.wait(1):
            with self.lock:
                if self.sync and not self.job["busy"] and time.time() >= self.next_sync:
                    self.start_job("export")

    def state(self):
        with self.lock:
            settings = copy.deepcopy(self.settings)
            source = os.path.abspath(os.path.expandvars(os.path.expanduser(settings["source"])))
            valid_preview = self.preview_source == (settings["provider"], source)
            return {"settings": settings, "defaults": copy.deepcopy(DEFAULT_RULES), "job": copy.deepcopy(self.job), "sync": self.sync,
                    "preview_count": len(self.preview) if valid_preview else 0, "preview_valid": valid_preview,
                    "next_sync": self.next_sync}


def make_server(studio, port=0):
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, status, data, content_type="application/json", cookie=False):
            body = json.dumps(data, ensure_ascii=False).encode() if content_type == "application/json" else data
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type + "; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if cookie:
                self.send_header("Set-Cookie", f"cv_session={token}; HttpOnly; SameSite=Strict; Path=/")
            self.end_headers()
            self.wfile.write(body)

        def authorized(self, api=False):
            expected = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != expected:
                return False
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + expected:
                return False
            if api:
                return secrets.compare_digest(self.headers.get("X-ConvoVault-Token", ""), token)
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get("Cookie", ""))
            except Exception:
                return False
            supplied = parse_qs(urlparse(self.path).query).get("token", [""])[0]
            return secrets.compare_digest(supplied or (cookie["cv_session"].value if "cv_session" in cookie else ""), token)

        def do_GET(self):
            path = urlparse(self.path).path
            if not self.authorized(path.startswith("/api/")):
                return self.respond(403, {"error": "Open Studio from its launcher to authenticate this browser"})
            try:
                params = parse_qs(urlparse(self.path).query)
                if path == "/api/state":
                    return self.respond(200, studio.state())
                if path == "/api/sources":
                    return self.respond(200, {"local": discover_sources(), "exports": EXPORT_SOURCES})
                if path == "/api/conversations":
                    mode = params.get("mode", ["preview"])[0]
                    query = params.get("q", [""])[0].casefold()
                    category = params.get("category", [""])[0]
                    with studio.lock:
                        settings = copy.deepcopy(studio.settings)
                        if mode == "library":
                            entries = search_library(settings["vault"], query, category)
                        else:
                            if not studio.state()["preview_valid"]:
                                entries = []
                            else:
                                entries = [describe(c, settings["rules"], settings["overrides"]) for c in studio.preview]
                                entries = [e for e in entries if (not category or e["classification"]["primary"] == category)
                                           and all(t in (e["title"] + " " + e["preview"]).casefold() for t in query.split())]
                    offset = max(0, int(params.get("offset", [0])[0]))
                    return self.respond(200, {"total": len(entries), "items": entries[offset:offset + 100],
                                              "categories": sorted(set(e["classification"]["primary"] for e in entries))})
                if path == "/api/note":
                    key = params.get("key", [""])[0]
                    mode = params.get("mode", ["preview"])[0]
                    with studio.lock:
                        if mode == "preview":
                            c = next((c for c in studio.preview if c.provider + ":" + c.conv_id == key), None)
                            if c is None or not studio.state()["preview_valid"]:
                                raise ValueError("Preview has changed; scan the source again")
                            content = render_steps(c.steps, studio.config())
                        else:
                            entries = search_library(studio.settings["vault"])
                            entry = next((e for e in entries if e["key"] == key), None)
                            if entry is None:
                                raise ValueError("Note not found")
                            content = safe_relative(studio.settings["vault"], entry["path"]).read_text(encoding="utf-8")
                    return self.respond(200, {"content": content})
                if path == "/":
                    page = (STATIC / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", token)
                    return self.respond(200, page, "text/html", cookie=True)
                filename = {"/app.js": "app.js", "/style.css": "style.css"}.get(path)
                if filename:
                    return self.respond(200, (STATIC / filename).read_bytes(), "text/javascript" if filename.endswith("js") else "text/css")
                self.respond(404, {"error": "Not found"})
            except Exception as exc:
                self.respond(400, {"error": str(exc)})

        def do_POST(self):
            if not self.authorized(True):
                return self.respond(403, {"error": "Unauthorized request"})
            try:
                length = int(self.headers.get("Content-Length", 0))
                if length < 0 or length > 2_000_000:
                    raise ValueError("Request too large")
                data = json.loads(self.rfile.read(length) or b"{}")
                path = urlparse(self.path).path
                if path == "/api/settings":
                    studio.save(data)
                elif path == "/api/preview":
                    studio.start_job("preview")
                elif path == "/api/export":
                    studio.start_job("export", data.get("selected"))
                elif path == "/api/sync":
                    with studio.lock:
                        studio.sync = bool(data.get("enabled"))
                        studio.next_sync = time.time() + studio.settings["sync_interval"]
                elif path == "/api/shutdown":
                    studio.stop.set()
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                elif path == "/api/browse":
                    kind = data.get("kind", "directory")
                    code = "import tkinter as t; from tkinter import filedialog as f; r=t.Tk(); r.withdraw(); r.attributes('-topmost',True); print(" + ("f.askopenfilename(filetypes=[('Conversation export','*.json *.jsonl *.zip *.db'),('All files','*.*')])" if kind == "file" else "f.askdirectory()") + "); r.destroy()"
                    args = [sys.executable, "-c", code]
                    # Frozen builds use a dedicated helper argument rather than executing -c.
                    import tempfile
                    output = None
                    if getattr(sys, "frozen", False):
                        fd, output = tempfile.mkstemp(prefix="convovault-picker-", suffix=".txt")
                        os.close(fd)
                        args = [sys.executable, "--pick", "file" if kind == "file" else "directory", "--pick-output", output]
                    try:
                        chosen = subprocess.run(args, capture_output=True, text=True, timeout=180,
                                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                        selected_path = Path(output).read_text(encoding="utf-8") if output else chosen.stdout.strip()
                    finally:
                        if output:
                            Path(output).unlink(missing_ok=True)
                    if chosen.returncode:
                        raise ValueError("Folder picker unavailable; paste the full path in the field")
                    return self.respond(200, {"path": selected_path})
                else:
                    return self.respond(404, {"error": "Not found"})
                self.respond(200, {"ok": True})
            except Exception as exc:
                self.respond(400, {"error": str(exc)})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server, f"http://127.0.0.1:{server.server_port}/?token={token}", token


def main(argv=None):
    parser = argparse.ArgumentParser(description="ConvoVault Studio")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--native", action="store_true", help="Use optional pywebview desktop window")
    parser.add_argument("--pick", choices=["file", "directory"], help=argparse.SUPPRESS)
    parser.add_argument("--pick-output", help=argparse.SUPPRESS)
    parser.add_argument("--settings-file", help="Use a separate Studio settings file")
    parser.add_argument("--connection-file", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.pick:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askopenfilename() if args.pick == "file" else filedialog.askdirectory()
        if args.pick_output:
            Path(args.pick_output).write_text(selected, encoding="utf-8")
        elif sys.stdout:
            print(selected)
        root.destroy()
        return
    studio = Studio(args.settings_file)
    server, url, _ = make_server(studio, args.port)
    if args.connection_file:
        atomic_text(args.connection_file, json.dumps({"url": url}))
    if sys.stdout:
        print("ConvoVault Studio: " + url, flush=True)
    try:
        if args.native:
            try:
                import webview
            except ImportError:
                raise SystemExit("Install the native window with: pip install '.[desktop]'")
            threading.Thread(target=server.serve_forever, daemon=True).start()
            webview.create_window("ConvoVault Studio", url, width=1440, height=950, min_size=(900, 650))
            webview.start()
        else:
            if not args.no_browser:
                webbrowser.open(url)
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        studio.stop.set()
        server.server_close()
        if args.connection_file:
            Path(args.connection_file).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
