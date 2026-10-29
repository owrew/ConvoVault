"""Safe multi-provider library, Markdown export, search and Obsidian maps."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

from .providers import get_provider
from .analysis.classification import DEFAULT_RULES, classify, validate_rules
from .analysis.intelligence import generate_intelligence
from .rendering.conversation import _format_step
from .providers.portable import timestamp
from .utils.content import TOOL_RESULT_TYPES


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def slug(value):
    value = re.sub(r'[<>:"/\\|?*\[\]#\x00-\x1f]', " ", str(value))
    value = re.sub(r"\s+", " ", value).strip(" .")[:75] or "Untitled"
    if value.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(10)], *[f"LPT{i}" for i in range(10)]}:
        value = "_" + value
    return value


def atomic_text(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".convovault-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def library_path(vault):
    return Path(vault) / "AI Vault" / ".convovault" / "library.json"


def load_library(vault):
    path = library_path(vault)
    if not path.exists():
        return {"version": 3, "conversations": {}, "artifacts": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 3 or not isinstance(data.get("conversations"), dict) or not isinstance(data.get("artifacts"), dict):
        raise ValueError("Unsupported or damaged library manifest; restore its backup before importing")
    return data


@contextmanager
def vault_lock(vault):
    path = library_path(vault).with_name("import.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ValueError("Another import is using this vault. If a previous process crashed, remove AI Vault/.convovault/import.lock after closing it.")
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


def safe_relative(vault, relative):
    root = Path(vault).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root / "AI Vault"):
        raise ValueError("Managed output must stay inside AI Vault")
    return path


def write_managed(vault, library, artifact_id, relative, content, stats):
    previous = library["artifacts"].get(artifact_id, {})
    relative = previous.get("path", relative)
    target = safe_relative(vault, relative)
    incoming = digest(content)
    if target.exists():
        actual = digest(target.read_text(encoding="utf-8"))
        if actual == incoming:
            library["artifacts"][artifact_id] = {"path": relative, "hash": incoming}
            stats["files_skipped"] += 1
            return relative
        if actual != previous.get("hash"):
            # User edits and pre-existing files remain intact, even with --force.
            stem = target.stem + " (import " + incoming[:8] + ")"
            candidate = target.with_name(stem + target.suffix)
            n = 2
            while candidate.exists() and digest(candidate.read_text(encoding="utf-8")) != incoming:
                candidate = target.with_name(stem + f" {n}" + target.suffix)
                n += 1
            target = candidate
            relative = target.relative_to(Path(vault).resolve()).as_posix()
            stats["conflicts"] += 1
    atomic_text(target, content)
    library["artifacts"][artifact_id] = {"path": relative, "hash": incoming}
    stats["files_written"] += 1
    return relative


def prepare_managed(vault, library, artifact_id, relative, stats):
    """Reserve edited-note copies before rendering links between generated notes."""
    previous = library["artifacts"].get(artifact_id, {})
    relative = previous.get("path", relative)
    target = safe_relative(vault, relative)
    if target.exists() and digest(target.read_text(encoding="utf-8")) != previous.get("hash"):
        counter = 1
        candidate = target.with_name(target.stem + " (ConvoVault import)" + target.suffix)
        while candidate.exists():
            counter += 1
            candidate = target.with_name(target.stem + f" (ConvoVault import {counter})" + target.suffix)
        relative = candidate.relative_to(Path(vault).resolve()).as_posix()
        library["artifacts"][artifact_id] = {"path": relative, "hash": None}
        stats["conflicts"] += 1
    return relative


def load_conversations(config):
    provider = get_provider(config.provider)
    if provider is None:
        raise ValueError("Unknown provider: " + config.provider)
    meta = provider.load_metadata_index(config)
    ids = provider.discover_conversations(config)
    selected = set(config.conv_filter) if config.conv_filter is not None else None
    conversations, warnings = [], list(getattr(provider, "warnings", []))
    for cid in ids:
        if selected is not None and cid not in selected:
            continue
        try:
            c = provider.read_conversation(cid, config)
            if c and c.steps:
                c.meta = c.meta or meta.get(cid)
                c.intelligence = generate_intelligence(c)
                conversations.append(c)
            else:
                warnings.append(f"{cid}: no readable messages")
        except Exception as exc:
            warnings.append(f"{cid}: {exc}")
    return conversations, warnings


def groups(steps, mode):
    if mode == "messages":
        return [[s] for s in steps]
    result, current = [], []
    for s in steps:
        if s.step_type == "USER_INPUT" and current:
            result.append(current)
            current = []
        current.append(s)
    if current:
        result.append(current)
    return result


def classify_conversation(c, rules, overrides):
    key = c.provider + ":" + c.conv_id
    text = (c.meta.title if c.meta else "") + "\n" + "\n".join(s.content for s in c.steps if s.step_type in ("USER_INPUT", "PLANNER_RESPONSE"))
    return classify(text, rules, overrides.get(key))


def describe(c, rules=None, overrides=None):
    classification = classify_conversation(c, rules, overrides or {})
    return {"id": c.conv_id, "key": c.provider + ":" + c.conv_id, "provider": c.provider,
            "title": c.meta.title if c.meta else c.conv_id, "steps": len(c.steps),
            "exchanges": len(groups(c.steps, "exchanges")), "source": c.source_file,
            "updated": (c.steps[-1].created_at if c.steps else "") or timestamp(c.meta.updated_at if c.meta else None), "classification": classification,
            "preview": next((s.content[:240] for s in c.steps if s.step_type == "USER_INPUT"), "")}


def frontmatter(data):
    # JSON scalars/arrays are valid YAML and safely escape arbitrary titles.
    return "---\n" + "\n".join(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in data.items()) + "\n---\n\n"


def render_steps(steps, config):
    body, results = [], [0]
    for s in steps:
        role = "User" if s.step_type == "USER_INPUT" else "Assistant" if s.step_type == "PLANNER_RESPONSE" else "System" if s.step_type == "SYSTEM_MESSAGE" else "Tool"
        body.append(f"### {role}" + (f" · {s.created_at}" if s.created_at else ""))
        if s.step_type == "SYSTEM_MESSAGE":
            body.append(s.content)
        else:
            formatted = _format_step(s, config.no_tool_results, config.max_tool_results_per_turn, results, config.max_tool_output_length)
            if not formatted and s.content and s.step_type not in TOOL_RESULT_TYPES:
                # Retain records introduced by new provider versions as plain text.
                formatted = s.content
            body.append(formatted)
    return "\n\n".join(body) + "\n"


def wikilink(path, label=None):
    clean = str(path).removesuffix(".md").replace("|", " ").replace("]", " ")
    label = str(label or Path(path).stem).replace("|", " ").replace("]", " ").replace("\n", " ")
    return f"[[{clean}|{label}]]"






