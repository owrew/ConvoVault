"""Regression and integration coverage for imports, safe exports and Studio."""
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

from convovault.analysis.classification import classify, validate_rules
from convovault.config.exporter import ExporterConfig
from convovault.discovery import discover_sources
from convovault.gui.server import Studio, make_server
from convovault.providers import get_provider
from convovault.providers.portable import chatgpt_steps, read_transcript
from convovault.workspace import export_library, load_library, load_conversations, safe_relative, search_library, groups


def message(role, content, **extra):
    return {"role": role, "content": content, **extra}


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source.json"
        self.vault = self.root / "vault"
        self.source.write_text(json.dumps([{"id": "same-id", "title": 'Python "notes" : شرح', "messages": [
            message("user", "Write a Python database API"), message("assistant", "Use SQLite. Firstanswer"),
            message("user", "بحث المصادر والشاملة"), message("assistant", "Secondanswer with research citation")]}]), encoding="utf-8")
        self.config = ExporterConfig(str(self.source), str(self.vault), "generic", note_mode="both")

    def tearDown(self):
        self.temp.cleanup()

    def test_generic_import_and_split_export(self):
        stats = export_library(self.config)
        self.assertEqual(stats["written"], 1)
        entry = load_library(self.vault)["conversations"]["generic:same-id"]
        self.assertEqual(len(entry["children"]), 2)
        first = (self.vault / entry["children"][0]).read_text(encoding="utf-8")
        second = (self.vault / entry["children"][1]).read_text(encoding="utf-8")
        self.assertIn("Firstanswer", first)
        self.assertNotIn("Secondanswer", first)
        self.assertIn("Secondanswer", second)
        self.assertIn('category: "Research"', second)
        self.assertIn('title: "Python \\"notes\\" : شرح"', (self.vault / entry["path"]).read_text(encoding="utf-8"))

    def test_idempotent_and_missing_note_recreated(self):
        export_library(self.config)
        second = export_library(self.config)
        self.assertEqual(second["files_written"], 0)
        self.assertEqual(second["skipped"], 1)
        entry = load_library(self.vault)["conversations"]["generic:same-id"]
        (self.vault / entry["children"][0]).unlink()
        self.assertEqual(export_library(self.config)["files_written"], 1)

    def test_source_and_user_edits_preserved(self):
        before = self.source.read_bytes()
        export_library(self.config)
        entry = load_library(self.vault)["conversations"]["generic:same-id"]
        path = self.vault / entry["path"]
        path.write_text("My edited note", encoding="utf-8")
        stats = export_library(self.config)
        self.assertGreaterEqual(stats["conflicts"], 1)
        self.assertEqual(path.read_text(encoding="utf-8"), "My edited note")
        self.assertEqual(self.source.read_bytes(), before)
        new_entry = load_library(self.vault)["conversations"]["generic:same-id"]
        self.assertNotEqual(entry["path"], new_entry["path"])

    def test_multiple_providers_keep_library_and_ids_separate(self):
        export_library(self.config)
        config = ExporterConfig(str(self.source), str(self.vault), "librechat")
        export_library(config)
        library = load_library(self.vault)
        self.assertEqual(len(library["conversations"]), 2)
        a, b = library["conversations"].values()
        self.assertNotEqual(a["path"], b["path"])
        self.assertIn("librechat", (self.vault / "AI Vault/Library.md").read_text())

    def test_chatgpt_selected_branch(self):
        mapping = {"root": {"parent": None, "children": ["u"]},
                   "u": {"parent": "root", "children": ["a", "b"], "message": {"author": {"role": "user"}, "content": {"parts": ["hello"]}}},
                   "a": {"parent": "u", "children": [], "message": {"author": {"role": "assistant"}, "content": {"parts": ["wrong branch"]}, "create_time": 2}},
                   "b": {"parent": "u", "children": [], "message": {"author": {"role": "assistant"}, "content": {"parts": ["selected answer"]}, "create_time": 3}}}
        self.assertEqual([s.content for s in chatgpt_steps(mapping, "a")], ["hello", "wrong branch"])
        self.assertEqual([s.content for s in chatgpt_steps(mapping)], ["hello", "selected answer"])
        mapping["root"]["parent"] = "a"
        self.assertLessEqual(len(chatgpt_steps(mapping, "a")), 3)

    def test_chatgpt_zip_import_without_extraction(self):
        path = self.root / "chatgpt.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("nested/conversations.json", json.dumps([{"id": "c", "title": "Chat", "messages": [message("user", "hello")]}]))
            archive.writestr("../../should-not-extract", "unsafe")
        config = ExporterConfig(str(path), str(self.vault), "chatgpt")
        conversations, warnings = load_conversations(config)
        self.assertEqual(len(conversations), 1)
        self.assertFalse(warnings)
        self.assertFalse((self.root / "should-not-extract").exists())

    def test_codex_response_items_avoid_event_duplicates(self):
        path = self.root / "rollout.jsonl"
        records = [{"type": "session_meta", "payload": {"id": "codex-id"}},
                   {"type": "event_msg", "payload": {"type": "user_message", "message": "hello"}},
                   {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hello"}]}},
                   {"type": "response_item", "payload": {"type": "function_call", "name": "read", "arguments": '{"path":"a.py"}'}},
                   {"type": "response_item", "payload": {"type": "function_call_output", "output": "tool result"}},
                   {"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "answer"}]}},
                   {"type": "event_msg", "payload": {"type": "agent_message", "message": "answer"}}]
        path.write_text("\n".join(json.dumps(r) for r in records) + '\n{"incomplete"', encoding="utf-8")
        c = read_transcript(path, "codex")
        self.assertEqual(c.conv_id, "codex-id")
        self.assertEqual(len(c.steps), 4)
        self.assertEqual(c.steps[1].tool_calls[0].name, "read")
        self.assertEqual(sum(s.content == "hello" for s in c.steps), 1)

    def test_codex_event_only_transcript(self):
        path = self.root / "events.jsonl"
        path.write_text(json.dumps({"type": "event_msg", "payload": {"type": "user_message", "message": "hello"}}), encoding="utf-8")
        self.assertEqual(read_transcript(path, "codex").steps[0].content, "hello")

    def test_codex_mixed_event_user_and_response_assistant(self):
        path = self.root / "mixed.jsonl"
        records = [{"type": "event_msg", "payload": {"type": "user_message", "message": "question"}},
                   {"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": "answer"}}]
        path.write_text("\n".join(json.dumps(r) for r in records))
        self.assertEqual([s.content for s in read_transcript(path, "codex").steps], ["question", "answer"])

    def test_same_title_without_ids_does_not_collapse(self):
        self.source.write_text(json.dumps([{"title": "Same", "messages": [message("user", "a")]},
                                                {"title": "Same", "messages": [message("user", "b")]}]))
        c, _ = load_conversations(self.config)
        self.assertEqual(len(c), 2)
        self.assertNotEqual(c[0].conv_id, c[1].conv_id)

    def test_codex_title_index(self):
        source = self.root / "codex"
        path = source / "sessions" / "s.jsonl"
        path.parent.mkdir(parents=True)
        rows = [{"type": "session_meta", "payload": {"id": "my-id"}}, {"type": "event_msg", "payload": {"type": "user_message", "message": "hello"}}]
        path.write_text("\n".join(json.dumps(r) for r in rows))
        (source / "session_index.jsonl").write_text(json.dumps({"id": "my-id", "thread_name": "My renamed chat"}))
        c, _ = load_conversations(ExporterConfig(str(source), str(self.vault), "codex"))
        self.assertEqual(c[0].meta.title, "My renamed chat")

    def test_preserved_parent_and_child_links_point_to_incoming_notes(self):
        export_library(self.config)
        entry = load_library(self.vault)["conversations"]["generic:same-id"]
        (self.vault / entry["path"]).write_text("My edit", encoding="utf-8")
        (self.vault / entry["children"][0]).write_text("My part edit", encoding="utf-8")
        export_library(self.config)
        updated = load_library(self.vault)["conversations"]["generic:same-id"]
        self.assertIn(updated["path"].removesuffix(".md"), (self.vault / updated["children"][0]).read_text(encoding="utf-8"))
        self.assertIn(updated["children"][0].removesuffix(".md"), (self.vault / updated["path"]).read_text(encoding="utf-8"))

    def test_background_scheduler_imports_changes_and_pauses(self):
        studio = Studio(self.root / "settings.json")
        studio.save({"provider": "generic", "source": str(self.source), "vault": str(self.vault)})
        studio.sync, studio.next_sync = True, 0
        try:
            deadline = time.time() + 5
            while time.time() < deadline and not load_library(self.vault)["conversations"]:
                time.sleep(.03)
            self.assertEqual(len(load_library(self.vault)["conversations"]), 1)
            while studio.job["busy"]:
                time.sleep(.01)
            self.source.write_text("damaged")
            studio.next_sync = 0
            deadline = time.time() + 5
            while time.time() < deadline and studio.sync:
                time.sleep(.03)
            self.assertFalse(studio.sync)
            self.assertTrue(studio.job["result"]["warnings"])
        finally:
            studio.stop.set()

    def test_codex_archives_and_paths(self):
        for folder, cid in [("sessions/2026/10", "a"), ("archived_sessions", "b")]:
            path = self.root / "codex" / folder / f"{cid}.jsonl"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"type": "event_msg", "payload": {"type": "user_message", "message": cid}}))
        c, w = load_conversations(ExporterConfig(str(self.root / "codex"), str(self.vault), "codex"))
        self.assertEqual(len(c), 2)
        self.assertFalse(w)

    def test_claude_export_content_and_tools(self):
        self.source.write_text(json.dumps([{"uuid": "claude", "name": "My chat", "chat_messages": [{"sender": "human", "text": "hello"}, {"sender": "assistant", "content": [{"type": "text", "text": "answer"}, {"type": "tool_use", "name": "read", "input": {}}]}]}]))
        c, w = load_conversations(ExporterConfig(str(self.source), str(self.vault), "claude"))
        self.assertEqual(c[0].steps[1].content, "answer")
        self.assertEqual(c[0].steps[1].tool_calls[0].name, "read")

    def test_claude_code_tools_are_not_prompts(self):
        path = self.root / "claude.jsonl"
        rows = [{"type": "user", "uuid": "u", "sessionId": "cc", "message": {"role": "user", "content": "hello"}},
                {"type": "assistant", "uuid": "a", "message": {"role": "assistant", "content": [{"type": "tool_use", "name": "read", "input": {}}]}},
                {"type": "user", "uuid": "t", "message": {"role": "user", "content": [{"type": "tool_result", "content": "result"}]}}]
        path.write_text("\n".join(json.dumps(r) for r in rows))
        c = read_transcript(path, "claude-code")
        self.assertEqual(sum(s.step_type == "USER_INPUT" for s in c.steps), 1)
        self.assertEqual(c.steps[-1].step_type, "RUN_COMMAND")

    def test_gemini_cli_json(self):
        self.source.write_text(json.dumps({"sessionId": "gem", "messages": [{"type": "user", "content": "hello"}, {"type": "gemini", "content": "answer"}]}))
        c, w = load_conversations(ExporterConfig(str(self.source), str(self.vault), "gemini"))
        self.assertEqual(c[0].steps[1].step_type, "PLANNER_RESPONSE")
        self.assertFalse(w)

    def test_provider_refresh_and_empty_source_does_not_leak_cache(self):
        reader = get_provider("chatgpt")
        reader.load_metadata_index(self.config)
        self.source.write_text(json.dumps([{"id": "new", "messages": [message("user", "new chat")]}]))
        self.assertEqual(reader.discover_conversations(self.config), ["new"])
        empty = self.root / "empty"
        empty.mkdir()
        self.assertFalse(reader.discover_conversations(ExporterConfig(str(empty), str(self.vault), "chatgpt")))

    def test_classification_arabic_boundaries_and_override(self):
        self.assertEqual(classify("بحث المصادر في الشاملة")["primary"], "Research")
        self.assertEqual(classify("unrelated phrase")["primary"], "Unsorted")
        rules = [{"name": "Go", "color": "#112233", "keywords": ["go"]}]
        self.assertEqual(classify("Google", rules)["primary"], "Unsorted")
        self.assertEqual(classify("go", rules, "Personal")["method"], "manual")
        with self.assertRaises(ValueError):
            validate_rules([{"name": "Bad", "color": "red", "keywords": []}])

    def test_messages_mode_retains_every_message(self):
        self.config.note_mode = "messages"
        export_library(self.config)
        entry = load_library(self.vault)["conversations"]["generic:same-id"]
        self.assertEqual(len(entry["children"]), 4)
        self.assertNotIn("Firstanswer", (self.vault / entry["path"]).read_text(encoding="utf-8"))
        self.assertEqual(len(search_library(self.vault, "Secondanswer")), 1)

    def test_canvas_references_existing_notes_and_unique_ids(self):
        export_library(self.config)
        for name in ("Brain.canvas", "Topics.canvas"):
            canvas = json.loads((self.vault / "AI Vault" / name).read_text(encoding="utf-8"))
            ids = [n["id"] for n in canvas["nodes"]]
            self.assertEqual(len(ids), len(set(ids)))
            for node in canvas["nodes"]:
                if node["type"] == "file":
                    self.assertTrue((self.vault / node["file"]).is_file())
            for edge in canvas["edges"]:
                self.assertIn(edge["fromNode"], ids)
                self.assertIn(edge["toNode"], ids)

    def test_manual_override_and_no_maps(self):
        self.config.category_overrides = {"generic:same-id": "Writing"}
        self.config.create_maps = False
        export_library(self.config)
        entry = load_library(self.vault)["conversations"]["generic:same-id"]
        self.assertEqual(entry["classification"]["primary"], "Writing")
        self.assertFalse((self.vault / "AI Vault/Brain.canvas").exists())

    def test_vault_path_traversal_rejected(self):
        with self.assertRaises(ValueError):
            safe_relative(self.vault, "../../escape.md")
        self.config.source_dir = str(self.root)
        with self.assertRaises(ValueError):
            export_library(self.config)

    def test_existing_root_indexes_untouched(self):
        self.vault.mkdir()
        (self.vault / "Topics.md").write_text("my existing index")
        export_library(self.config)
        self.assertEqual((self.vault / "Topics.md").read_text(), "my existing index")

    def test_damaged_library_is_not_overwritten(self):
        path = self.vault / "AI Vault/.convovault/library.json"
        path.parent.mkdir(parents=True)
        path.write_text("broken")
        with self.assertRaises(ValueError):
            export_library(self.config)
        self.assertEqual(path.read_text(), "broken")

    def test_malformed_file_is_reported(self):
        self.source.write_text("broken")
        conversations, warnings = load_conversations(self.config)
        self.assertFalse(conversations)
        self.assertEqual(len(warnings), 1)
        self.assertFalse(self.vault.exists())

    def test_discovery_uses_supplied_home(self):
        paths = discover_sources(self.root)
        self.assertTrue(any(p["provider"] == "gemini" for p in paths))

    def test_cli_switches_to_the_selected_providers_default_path(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from importlib import import_module
        cli_module = import_module("convovault.cli.main")
        _resolve_paths = cli_module._resolve_paths
        with patch.dict("os.environ", {}, clear=True), patch.object(cli_module, "_load_saved_config", return_value={"provider": "antigravity", "source": "old-source"}), patch.object(cli_module, "_detect_source", return_value="codex-source") as detect:
            provider, source, _ = _resolve_paths(SimpleNamespace(provider="codex", source=None, vault=str(self.vault)))
        self.assertEqual((provider, source), ("codex", "codex-source"))
        detect.assert_called_once_with("codex")

    def test_openwebui_read_only(self):
        path = self.root / "webui.db"
        db = sqlite3.connect(path)
        db.execute("CREATE TABLE chat (id TEXT, title TEXT, chat TEXT, created_at INT)")
        db.execute("INSERT INTO chat VALUES (?, ?, ?, ?)", ("w", "WebUI", json.dumps({"messages": [message("user", "hello")]}), 1))
        db.commit()
        db.close()
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        convs, warnings = load_conversations(ExporterConfig(str(path), str(self.vault), "openwebui"))
        self.assertEqual(len(convs), 1)
        self.assertFalse(warnings)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)

    def test_api_auth_origin_preview_and_export(self):
        studio = Studio(self.root / "studio.json")
        studio.save({"source": str(self.source), "vault": str(self.vault), "provider": "generic"})
        server, url, token = make_server(studio)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = url.split("/?")[0]
        def request(path, payload=None, authorized=True, origin=None):
            headers = {"X-ConvoVault-Token": token} if authorized else {}
            if origin:
                headers["Origin"] = origin
            req = Request(base + path, data=json.dumps(payload).encode() if payload is not None else None, headers=headers)
            with urlopen(req, timeout=10) as response:
                return json.load(response)
        try:
            with self.assertRaises(HTTPError) as unauthorized:
                request("/api/state", authorized=False)
            self.assertEqual(unauthorized.exception.code, 403)
            unauthorized.exception.close()
            with self.assertRaises(HTTPError) as origin_error:
                request("/api/settings", {}, origin="https://example.com")
            origin_error.exception.close()
            request("/api/preview", {})
            for _ in range(200):
                if not request("/api/state")["job"]["busy"]:
                    break
                time.sleep(.01)
            self.assertFalse(self.vault.exists())
            previews = request("/api/conversations?mode=preview")
            self.assertEqual(previews["total"], 1)
            request("/api/export", {"selected": ["same-id"]})
            for _ in range(200):
                if not request("/api/state")["job"]["busy"]:
                    break
                time.sleep(.01)
            self.assertEqual(request("/api/conversations?mode=library")["total"], 1)
            self.assertFalse(request("/api/state")["job"]["error"])
        finally:
            studio.stop.set()
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
