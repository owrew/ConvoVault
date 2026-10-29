"""Read-only, dependency-free adapters for portable exports and local transcripts.

No browser cookies, credentials, encrypted caches or cloud accounts are accessed.
Unknown record types are ignored; unsupported attachments get explicit markers.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
import zipfile
from collections import Counter

from .base import BaseProvider
from ..models import Conversation, ConversationMeta, Step, ToolCall

log = logging.getLogger(__name__)
MAX_JSON_BYTES = 512 * 1024 * 1024


def timestamp(value):
    if isinstance(value, (float, int)):
        try:
            return datetime.fromtimestamp(value / 1000 if value > 1e12 else value, timezone.utc).isoformat()
        except (ValueError, OverflowError, OSError):
            return ""
    return str(value or "")


def text_content(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(filter(None, (text_content(v) for v in value)))
    if isinstance(value, dict):
        for key in ("text", "parts", "content", "result", "output"):
            if key in value:
                return text_content(value[key])
        if "asset_pointer" in value or value.get("type") in ("image", "image_url", "image_asset_pointer", "input_image"):
            return "[Image attachment: original source required]"
        if value.get("type") in ("audio", "input_audio", "video"):
            return "[Media attachment: original source required]"
    return ""


def step(role, content, when="", tools=None):
    role = {"human": "user", "model": "assistant"}.get(role, role)
    kind = {"user": "USER_INPUT", "assistant": "PLANNER_RESPONSE", "tool": "RUN_COMMAND",
            "system": "SYSTEM_MESSAGE", "developer": "SYSTEM_MESSAGE"}.get(role)
    if not kind:
        return None
    return Step(0, "USER_EXPLICIT" if role == "user" else role.upper(), kind,
                "DONE", timestamp(when), text_content(content), tool_calls=tools or [])


def make_conversation(cid, title, steps, provider, path, created=None, updated=None):
    steps = [s for s in steps if s and (s.content or s.tool_calls)]
    if not steps:
        return None
    for i, s in enumerate(steps):
        s.index = i
    cid = str(cid or hashlib.sha256((str(path) + str(title)).encode()).hexdigest()[:24])
    meta = ConversationMeta(cid, str(title or cid[:12]), len(steps))
    for attr, value in (("created_at", created), ("updated_at", updated)):
        try:
            setattr(meta, attr, int(float(value)) if isinstance(value, (int, float)) else
                    int(datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()))
        except (ValueError, TypeError, OverflowError):
            pass
    return Conversation(cid, provider, steps, str(path), meta)


def chatgpt_steps(mapping, current_node=None):
    """Follow the selected branch. Never interleave regenerated alternatives."""
    if not isinstance(mapping, dict) or not mapping:
        return []
    if current_node not in mapping:
        leaves = [k for k, v in mapping.items() if not v.get("children")]
        current_node = max(leaves or mapping, key=lambda k: float(
            ((mapping[k].get("message") or {}).get("create_time") or 0)))
    seen, chain = set(), []
    while current_node in mapping and current_node not in seen:
        seen.add(current_node)
        node = mapping[current_node]
        chain.append(node)
        current_node = node.get("parent")
    result = []
    for node in reversed(chain):
        msg = node.get("message") or {}
        if (msg.get("metadata") or {}).get("is_visually_hidden_from_conversation"):
            continue
        s = step((msg.get("author") or {}).get("role"), msg.get("content"), msg.get("create_time"))
        if s:
            result.append(s)
    return result


def read_json_export(data, provider, path):
    if isinstance(data, dict):
        if isinstance(data.get("conversations"), list):
            data = data["conversations"]
        elif isinstance(data.get("chats"), list):
            data = data["chats"]
        else:
            data = [data]
    if not isinstance(data, list):
        raise ValueError("Expected a conversation object or a list of conversations")
    conversations = []
    for position, obj in enumerate(data):
        if not isinstance(obj, dict):
            continue
        title = obj.get("title") or obj.get("name") or obj.get("summary")
        cid = obj.get("id") or obj.get("uuid") or obj.get("conversationId") or obj.get("sessionId")
        cid = cid or hashlib.sha256(f"{path}:{position}".encode()).hexdigest()[:24]
        if provider == "chatgpt" and "mapping" in obj:
            steps = chatgpt_steps(obj["mapping"], obj.get("current_node"))
        else:
            messages = obj.get("chat_messages", obj.get("messages", obj.get("chat", [])))
            if isinstance(messages, dict):
                messages = messages.get("messages", [])
            steps = []
            for msg in messages if isinstance(messages, list) else []:
                if not isinstance(msg, dict):
                    continue
                role = msg.get("role") or msg.get("sender") or msg.get("type")
                if role is None and "isCreatedByUser" in msg:
                    role = "user" if msg["isCreatedByUser"] else "assistant"
                content = msg.get("content") or msg.get("text") or msg.get("message") or ""
                tools = []
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            tools.append(ToolCall(block.get("name", "tool"), block.get("input", {})))
                s = step(role, content, msg.get("created_at") or msg.get("timestamp"), tools)
                if s:
                    if role == "gemini" and isinstance(msg.get("thoughts"), list):
                        s.thinking = text_content(msg["thoughts"])
                    steps.append(s)
            # Gemini CLI uses type=gemini for assistant responses.
            if provider == "gemini":
                steps = []
                for msg in messages if isinstance(messages, list) else []:
                    s = step("assistant" if msg.get("type") == "gemini" else msg.get("type", msg.get("role")),
                             msg.get("content", msg.get("text", "")), msg.get("timestamp"))
                    if s:
                        steps.append(s)
        if not title:
            title = next((s.content.splitlines()[0][:100] for s in steps if s and s.step_type == "USER_INPUT" and s.content), "Untitled chat")
        c = make_conversation(cid, title, steps, provider, path,
                              obj.get("create_time", obj.get("created_at", obj.get("startTime"))),
                              obj.get("update_time", obj.get("updated_at", obj.get("lastUpdated"))))
        if c:
            conversations.append(c)
    return conversations


def read_transcript(path, provider):
    responses, events = [], []
    order = {}
    warnings = []
    cid, title, seen_ids = None, None, set()
    with Path(path).open(encoding="utf-8-sig") as fh:
        for line_no, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                log.warning("Skipping incomplete JSONL record %s:%s", path, line_no)
                warnings.append(f"{Path(path).name}:{line_no}: incomplete JSONL record skipped")
                continue
            if not isinstance(row, dict):
                warnings.append(f"{Path(path).name}:{line_no}: unsupported JSONL record skipped")
                continue
            payload = row.get("payload") or {}
            when = row.get("timestamp", "")
            if row.get("type") == "session_meta":
                cid = payload.get("id") or payload.get("session_id")
            if provider == "codex":
                if row.get("type") == "response_item":
                    kind = payload.get("type")
                    s = None
                    if kind == "message":
                        # System/developer instructions are application context, not chat messages.
                        if payload.get("role") in ("user", "assistant"):
                            s = step(payload["role"], payload.get("content"), when)
                    elif kind in ("function_call", "custom_tool_call"):
                        args = payload.get("arguments", payload.get("input", ""))
                        try:
                            args = json.loads(args) if isinstance(args, str) else args
                        except ValueError:
                            args = {"input": args}
                        if not isinstance(args, dict):
                            args = {"input": args}
                        s = step("assistant", "", when, [ToolCall(payload.get("name", "tool"), args)])
                    elif kind in ("function_call_output", "custom_tool_call_output"):
                        s = step("tool", payload.get("output", ""), when)
                    if s:
                        responses.append(s)
                        order[id(s)] = line_no
                elif row.get("type") == "event_msg":
                    kind = payload.get("type")
                    if kind in ("user_message", "agent_message"):
                        s = step("user" if kind == "user_message" else "assistant", payload.get("message", ""), when)
                        if s:
                            events.append(s)
                            order[id(s)] = line_no
            else:  # Claude Code JSONL
                cid = row.get("sessionId") or cid
                msg = row.get("message") or {}
                if row.get("type") not in ("user", "assistant") or not isinstance(msg, dict):
                    continue
                mid = row.get("uuid")
                if mid and mid in seen_ids:
                    continue
                if mid:
                    seen_ids.add(mid)
                for block in msg.get("content", []) if isinstance(msg.get("content"), list) else []:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        responses.append(step("tool", block.get("content", ""), when))
                content = msg.get("content", "")
                tools = [ToolCall(b.get("name", "tool"), b.get("input", {})) for b in content
                         if isinstance(b, dict) and b.get("type") == "tool_use"] if isinstance(content, list) else []
                # Tool-only user envelopes are not new human prompts.
                visible = [b for b in content if not isinstance(b, dict) or b.get("type") != "tool_result"] if isinstance(content, list) else content
                s = step(msg.get("role", row["type"]), visible, when, tools)
                if s and (s.content or s.tool_calls):
                    responses.append(s)
    if provider == "codex":
        counts = Counter((s.step_type, s.content) for s in responses)
        missing = []
        for s in events:
            key = (s.step_type, s.content)
            if counts[key]:
                counts[key] -= 1
            else:
                missing.append(s)
        steps = sorted(responses + missing, key=lambda s: order[id(s)])
    else:
        steps = responses
    title = next((s.content.splitlines()[0][:100] for s in steps if s and s.step_type == "USER_INPUT" and s.content), Path(path).stem)
    c = make_conversation(cid or Path(path).stem, title, steps, provider, path)
    if c:
        c.import_warnings = warnings
    return c


class PortableProvider(BaseProvider):
    provider_name = "generic"

    def __init__(self):
        self._signature = None
        self._source = None
        self._conversations = {}
        self.warnings = []

    @property
    def name(self):
        return self.provider_name

    def _files(self, source):
        path = Path(source)
        if path.is_file():
            return [path]
        if not path.is_dir():
            raise ValueError("Source does not exist: " + str(path))
        if self.name == "codex":
            roots = [p for p in (path / "sessions", path / "archived_sessions") if p.is_dir()] or [path]
            return sorted({p for root in roots for p in root.rglob("*.jsonl")})
        if self.name == "claude-code":
            path = path / "projects" if (path / "projects").is_dir() else path
            return sorted(path.rglob("*.jsonl"))
        if self.name == "gemini":
            return sorted(path.rglob("session-*.json"))
        candidate = path / "conversations.json"
        return [candidate] if candidate.is_file() else sorted(path.glob("*.json"))

    def _load(self, config):
        files = self._files(config.source_dir)
        signature = [(str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in files]
        if signature == self._signature:
            return
        conversations, self.warnings = {}, []
        for path in files:
            try:
                if path.suffix.lower() == ".jsonl":
                    c = read_transcript(path, self.name)
                    self.warnings.extend(getattr(c, "import_warnings", []))
                    items = [c] if c else []
                elif path.suffix.lower() == ".zip":
                    with zipfile.ZipFile(path) as archive:
                        members = [m for m in archive.infolist() if Path(m.filename).name == "conversations.json"]
                        if not members:
                            raise ValueError("ZIP does not contain conversations.json")
                        member = members[0]
                        if member.file_size > MAX_JSON_BYTES:
                            raise ValueError("Export exceeds the 512 MB safety limit; extract and split the JSON first")
                        items = read_json_export(json.loads(archive.read(member).decode("utf-8-sig")), self.name, path)
                else:
                    if path.stat().st_size > MAX_JSON_BYTES:
                        raise ValueError("JSON exceeds the 512 MB limit")
                    with path.open(encoding="utf-8-sig") as fh:
                        items = read_json_export(json.load(fh), self.name, path)
                for c in items:
                    previous = conversations.get(c.conv_id)
                    if previous is None or len(c.steps) > len(previous.steps):
                        conversations[c.conv_id] = c
            except (ValueError, OSError, zipfile.BadZipFile, TypeError, AttributeError) as exc:
                self.warnings.append(f"{path.name}: {exc}")
                log.warning("Cannot import %s: %s", path, exc)
        if self.name == "codex":
            source = Path(config.source_dir)
            for base in [source, *list(source.parents)[:6]]:
                index = base / "session_index.jsonl"
                if index.is_file():
                    try:
                        for line in index.read_text(encoding="utf-8").splitlines():
                            try:
                                record = json.loads(line)
                            except ValueError:
                                continue
                            cid = record.get("id")
                            if cid in conversations and record.get("thread_name"):
                                conversations[cid].meta.title = record["thread_name"]
                    except OSError as exc:
                        self.warnings.append(f"Title index: {exc}")
                    break
        self._conversations, self._signature = conversations, signature
        self._source = config.source_dir

    def discover_conversations(self, config):
        self._load(config)
        return sorted(self._conversations)

    def load_metadata_index(self, config):
        self._load(config)
        return {key: c.meta for key, c in self._conversations.items()}

    def read_conversation(self, conv_id, config):
        if self._source != config.source_dir:
            self._load(config)
        return self._conversations.get(conv_id)


def adapter(name):
    return type(name.replace("-", "_").title() + "Provider", (PortableProvider,), {"provider_name": name})
