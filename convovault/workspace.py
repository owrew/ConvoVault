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


def build_canvas(entries, layout):
    entries = sorted(entries, key=lambda e: (e["classification"]["primary"], e["key"]))
    total = len(entries)
    radius, coordinates = 1, []
    while len(coordinates) < math.ceil(total / 2):
        coordinates = [(col, row) for row in range(-radius, radius + 1) for col in range(radius + 1)
                       if (col / (radius + .5)) ** 2 + (row / (radius + .5)) ** 2 <= 1]
        if len(coordinates) < math.ceil(total / 2):
            radius += 1
    coordinates = sorted(sorted(coordinates, key=lambda p: p[0] ** 2 + p[1] ** 2)[:math.ceil(total / 2)], key=lambda p: (p[1], p[0]))
    nodes = [{"id": "legend", "type": "text", "text": f"# ConvoVault · {layout.title()} map\n{total} conversations. Colors represent categories.\nOpen a card to read its note. Brain is a stylized two-hemisphere layout.", "x": -400, "y": -radius * 250 - 400 if layout == "brain" else -350, "width": 800, "height": 150}]
    edges, hubs = [], {}
    categories = sorted(set(e["classification"]["primary"] for e in entries))
    for i, category in enumerate(categories):
        hubs[category] = "category-" + digest(category)[:12]
        nodes.append({"id": hubs[category], "type": "text", "text": "## " + category,
                      "x": (radius + 3) * 420 if layout == "brain" else i * 760,
                      "y": i * 150 - len(categories) * 75 if layout == "brain" else -150,
                      "width": 300, "height": 100,
                      "color": next(e["classification"]["color"] for e in entries if e["classification"]["primary"] == category)})
    for i, entry in enumerate(entries):
        if layout == "brain":
            side = -1 if i % 2 == 0 else 1
            col, row = coordinates[i // 2]
            x = 280 + col * 420 if side == 1 else -620 - col * 420
            y = row * 250
        else:
            category_index = categories.index(entry["classification"]["primary"])
            siblings = [e for e in entries[:i] if e["classification"]["primary"] == entry["classification"]["primary"]]
            x, y = category_index * 760, len(siblings) * 250
        nid = "chat-" + digest(entry["key"])[:16]
        nodes.append({"id": nid, "type": "file", "file": entry["path"], "x": int(x), "y": int(y),
                      "width": 340, "height": 190, "color": entry["classification"]["color"]})
        edges.append({"id": "edge-" + nid, "fromNode": hubs[entry["classification"]["primary"]], "toNode": nid,
                      "color": entry["classification"]["color"], "toEnd": "none"})
    return {"nodes": nodes, "edges": edges}


def export_library(config):
    rules = validate_rules(config.classification_rules if config.classification_rules is not None else DEFAULT_RULES)
    conversations, warnings = load_conversations(config)
    stats = {"written": 0, "skipped": 0, "failed": len(warnings), "total": len(conversations),
             "files_written": 0, "files_skipped": 0, "conflicts": 0, "warnings": warnings}
    if not conversations:
        if not warnings:
            stats["warnings"].append("No conversations found. Choose a supported export or local session folder.")
        return stats
    source, vault = Path(config.source_dir).resolve(), Path(config.vault_dir).resolve()
    if vault == source or vault.is_relative_to(source) or source.is_relative_to(vault / "AI Vault"):
        raise ValueError("Choose a vault separate from the source folder to prevent importing generated notes")
    with vault_lock(vault):
        library = load_library(vault)
        known = dict(library["conversations"])
        for c in conversations:
            entry = describe(c, rules, config.category_overrides)
            entry["technologies"] = c.intelligence.technologies
            entry["topics"] = c.intelligence.topics
            entry["summary"] = c.intelligence.summary
            base = f"{slug(entry['title'])}--{digest(entry['key'])[:12]}"
            entry["path"] = prepare_managed(vault, library, entry["key"], f"AI Vault/Chats/{c.provider}/{base}.md", stats)
            known[entry["key"]] = entry
        hub_paths = {}
        for entry in known.values():
            names = [entry["classification"]["primary"]] + entry.get("technologies", [])
            for name in names:
                if name not in hub_paths:
                    hub_paths[name] = prepare_managed(vault, library, "hub:" + name,
                                                      f"AI Vault/Topics/{slug(name)}--{digest(name)[:8]}.md", stats)
        for c in conversations:
            entry = known[c.provider + ":" + c.conv_id]
            key = entry["key"]
            base = f"{slug(entry['title'])}--{digest(key)[:12]}"
            classification = entry["classification"]
            common = {"id": key, "title": entry["title"], "source": c.provider, "conversation_id": c.conv_id,
                      "category": classification["primary"], "categories": classification["categories"],
                      "classification_method": classification["method"], "tags": ["ai-chat", c.provider, "category/" + re.sub(r"\W+", "-", classification["primary"].lower()).strip("-")],
                      "created": c.steps[0].created_at or timestamp(c.meta.created_at if c.meta else None), "updated": entry["updated"]}
            old_files_written = stats["files_written"]
            children = []
            if config.note_mode != "conversation":
                mode = "messages" if config.note_mode == "messages" else "exchanges"
                chunks = groups(c.steps, mode)
                parent_path = entry["path"]
                planned_children = [prepare_managed(vault, library, f"{key}:{mode}:{number}",
                                    f"AI Vault/{mode.title()}/{c.provider}/{digest(key)[:12]}/{number:04}.md", stats)
                                    for number in range(1, len(chunks) + 1)]
                for number, chunk in enumerate(chunks, 1):
                    title = f"{entry['title']} · {mode[:-1]} {number}"
                    part_class = classify("\n".join(s.content for s in chunk), rules)
                    metadata = {**common, "id": f"{key}:{mode}:{number}", "title": title, "category": part_class["primary"],
                                "categories": part_class["categories"], "classification_method": part_class["method"],
                                "tags": ["ai-chat", c.provider, "category/" + re.sub(r"\W+", "-", part_class["primary"].lower()).strip("-")],
                                "note_type": mode[:-1], "sequence": number,
                                "created": chunk[0].created_at, "updated": chunk[-1].created_at}
                    content = frontmatter(metadata) + f"# {title}\n\n" + "Conversation: " + wikilink(parent_path, entry["title"]) + "\n\n" + render_steps(chunk, config)
                    navigation = []
                    if number > 1:
                        navigation.append(wikilink(planned_children[number - 2], "Previous part"))
                    if number < len(chunks):
                        navigation.append(wikilink(planned_children[number], "Next part"))
                    content += "\n" + " · ".join(navigation) + "\n"
                    relative = planned_children[number - 1]
                    actual = write_managed(vault, library, f"{key}:{mode}:{number}", relative, content, stats)
                    children.append(actual)
            common["note_type"] = "conversation" if config.note_mode in ("conversation", "both") else "conversation-index"
            content = frontmatter(common) + f"# {entry['title']}\n\n"
            content += f"Provider: {c.provider}  \nCategory: {classification['primary']} ({classification['method']})\n\n"
            names = [classification["primary"]] + entry["technologies"]
            content += "Connections: " + " · ".join(wikilink(hub_paths[name], name) for name in dict.fromkeys(names)) + "\n\n"
            if c.intelligence.summary:
                content += "## Extractive overview\n\n" + c.intelligence.summary + "\n\n"
            similar = []
            for other_key, other in known.items():
                if other_key == key:
                    continue
                shared = set(entry["technologies"]) & set(other.get("technologies", []))
                if shared:
                    similar.append((len(shared), other, shared))
            if similar:
                content += "## Related conversations\n\n"
                for _, other, shared in sorted(similar, key=lambda row: (-row[0], row[1]["key"]))[:5]:
                    content += "- " + wikilink(other["path"], other["title"]) + " — shared technologies: " + ", ".join(sorted(shared)) + "\n"
                content += "\n"
            if classification["evidence"]:
                content += "Matched phrases: " + "; ".join(f"{name}: {', '.join(hits)}" for name, hits in classification["evidence"].items()) + "\n\n"
            if children:
                content += "## Linked notes\n\n" + "\n".join(f"- {wikilink(p, f'Part {i}')}" for i, p in enumerate(children, 1)) + "\n\n"
            if config.note_mode in ("conversation", "both"):
                content += render_steps(c.steps, config)
            content += f"\nSource transcript: `{c.source_file}`\n\n*Generated by ConvoVault 3. Source files are read-only.*\n"
            entry["path"] = write_managed(vault, library, key, f"AI Vault/Chats/{c.provider}/{base}.md", content, stats)
            entry["children"] = children
            entry["note_mode"] = config.note_mode
            library["conversations"][key] = entry
            stats["written" if stats["files_written"] > old_files_written else "skipped"] += 1
        entries = list(library["conversations"].values())
        for name, relative in hub_paths.items():
            matching = [entry for entry in entries if entry["classification"]["primary"] == name or name in entry.get("technologies", [])]
            text = frontmatter({"note_type": "topic", "title": name}) + "# " + name + "\n\n"
            text += "\n".join("- " + wikilink(entry["path"], entry["title"]) for entry in matching) + "\n"
            write_managed(vault, library, "hub:" + name, relative, text, stats)
        lines = ["# ConvoVault library", "", f"{len(entries)} conversations across all imported sources.", "",
                 "[[AI Vault/Brain.canvas|Brain map]] · [[AI Vault/Topics.canvas|Topic map]]", ""]
        for category in sorted(set(e["classification"]["primary"] for e in entries)):
            lines += ["## " + category, ""]
            for entry in sorted(entries, key=lambda e: e.get("updated", ""), reverse=True):
                if entry["classification"]["primary"] == category:
                    lines.append(f"- {wikilink(entry['path'], entry['title'])} ({entry['provider']})")
            lines.append("")
        write_managed(vault, library, "index:library", "AI Vault/Library.md", "\n".join(lines), stats)
        if config.create_maps:
            for layout, filename in (("brain", "Brain.canvas"), ("topics", "Topics.canvas")):
                # A very large vault remains usable through the complete Markdown library.
                limit = 500
                if len(entries) > limit:
                    stats["warnings"].append(f"{filename}: showing the 500 most recent conversations; Library.md contains all")
                mapped = sorted(entries, key=lambda e: e.get("updated", ""), reverse=True)[:limit]
                write_managed(vault, library, "map:" + layout, "AI Vault/" + filename,
                              json.dumps(build_canvas(mapped, layout), ensure_ascii=False, indent=2) + "\n", stats)
        graph_guide = "# Color your Obsidian graph\n\nOpen Graph view → settings → Groups → New group. Use the following searches and colors.\n\n"
        for rule in rules:
            tag = re.sub(r"\W+", "-", rule["name"].lower()).strip("-")
            graph_guide += f"- `tag:#category/{tag}` — {rule['color']} ({rule['name']})\n"
        graph_guide += "\nThe normal graph uses Obsidian's force layout. Open Brain.canvas for a fixed stylized brain layout, or Topics.canvas for category columns. No existing Obsidian settings are changed.\n"
        write_managed(vault, library, "guide:graph", "AI Vault/Graph colors.md", graph_guide, stats)
        # Keep the previous manifest for crash recovery. Sources and edited notes are never deleted.
        manifest = library_path(vault)
        if manifest.exists():
            atomic_text(manifest.with_suffix(".previous.json"), manifest.read_text(encoding="utf-8"))
        atomic_text(manifest, json.dumps(library, ensure_ascii=False, indent=2) + "\n")
    stats["library_total"] = len(entries)
    stats["vault"] = str(vault)
    return stats


def search_library(vault, query="", category="", provider=""):
    library = load_library(vault)
    matches = []
    terms = query.casefold().split()
    for entry in library["conversations"].values():
        if category and entry["classification"]["primary"] != category or provider and entry["provider"] != provider:
            continue
        text = entry["title"] + "\n" + entry.get("preview", "")
        if terms:
            for relative in [entry["path"]] + entry.get("children", []):
                path = safe_relative(vault, relative)
                if path.exists():
                    text += "\n" + path.read_text(encoding="utf-8")
        if all(term in text.casefold() for term in terms):
            matches.append(entry)
    return sorted(matches, key=lambda e: e.get("updated", ""), reverse=True)
