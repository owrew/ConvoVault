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




















