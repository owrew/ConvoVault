"""Publish the reviewed Studio 3.0 changes as separate feature commits in one run.

Default: display the plan. Use --apply to commit, and --push to publish afterwards.
This is a one-time, base-pinned migration script; repeat application is refused.
No credentials are read into Python or written to disk. Git uses its configured helper.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
REMOTE = "https://github.com/owrew/ConvoVault.git"
BASE = "196a31ed6299bbe9b575553016b1ac1f219db201"
BRANCH = "main"
SELF = "scripts/publish-feature-commits.py"
EXPECTED = {'.gitignore': '2224b5d59578e8dc778e7eb6d1055183399fb7b4bf5c585c69cdecdf1f73ae96', 'CHANGELOG.md': '0a04776b8fa75904c464e2202e2d577f314399eb91a2443d70fdf770baf9c45f', 'MIGRATION.md': 'e81cb2805ad8c3fc2c2462400abde17ab7f3b613f4b217052519bcbc027cf370', 'README.md': '3d9226c5a989af0bb9ec034c82afe97c6b6802f5aad671b77974e9707c0957c0', 'Start-Studio.cmd': 'bc3ce7573f3939c1d62417413a463deb92ae8906a79138f02f2ed03271ec0db7', 'convovault/__init__.py': '72aadcfa5b6e6641a81f44c7a650f1e6dfd56f2974832868cbcdfd9027b10b75', 'convovault/analysis/classification.py': 'a7828594bc17350e3a80f348ae7fdaa73be4894913eb635206223ba606829253', 'convovault/analysis/intelligence.py': 'ee537c865bc5bdf8d66a2225c66f069cf342138f4ab586d6148a59dea275616f', 'convovault/cli/main.py': '88b3b32ed18f8184c32a190887eae0d1698935032fb9413d2beda0a34a7a0f8f', 'convovault/config/exporter.py': '506742f594b1a55d1a5c6cc0d77a6830608891cd98d643d498b8952c869ab070', 'convovault/discovery.py': 'b6e9dcca7c225daf85641023f89cde158dca79b30a9fe549db6ddf233ced8f65', 'convovault/exporter/engine.py': '6d6134dd1a695780023c52ff0b021e823da83da66251b06588085aa8628d574b', 'convovault/gui/__init__.py': '3fd61c8fb669ffa07b5c6928373615e23244fcde62699fec4a85ff61c200d38b', 'convovault/gui/server.py': 'eff33e11d5d19077bb1ae00dc8acb57d9e0f5aefcb20d193391c4c2548480273', 'convovault/gui/static/app.js': 'f9458cd60a4055b33d30e0f9076b9780ae7146ca1bdf382c8b6dbb85d739ff3d', 'convovault/gui/static/index.html': 'b30585d69eec415894f62474992ede206e28cce31bc4cd9a82eaec92ca343ef7', 'convovault/gui/static/style.css': '8321a590742f5990802d1352c6f61d052a71905e68aae33db73f3cc3b6aecce9', 'convovault/providers/chatgpt/chatgpt.py': '1c1a11f92832bca70dd6d3a104c8cb69ed31a1c02e62e92c6fb59823abd54f50', 'convovault/providers/chatgpt/provider.py': '5e1196465c642601579c5d4da3cc346f8a9cf96a3b592e3d84f13a8daa1cf8bf', 'convovault/providers/claude/claude_ai.py': '07e0214a221dcd38258441ca186adf0320a8b2d0b71518f62c644e28c16a205e', 'convovault/providers/claude/provider.py': '2b197fbd6957cdc7c0f98a63cec91fc2f5f735dfa34894b4ec9ea647cfdb73d5', 'convovault/providers/gemini/provider.py': '9ab62f0657ffb6a78d1c04ddc79261790072ece06a1446a11a99c6d21f2f73e5', 'convovault/providers/librechat/provider.py': '47800c0487d2239a4dab29d55a05ae9c5b69a9766b13215929df8b6e025b5e59', 'convovault/providers/ollama/ollama.py': 'd103c0460002df86cfbf2d9aa5116209bf22f1ca7a911dc428b029b9d2da1017', 'convovault/providers/openwebui/ollama.py': 'd103c0460002df86cfbf2d9aa5116209bf22f1ca7a911dc428b029b9d2da1017', 'convovault/providers/plugin_loader.py': '5a478b54af272b8fbd8d923027a184e64e6c4ff50d600712a4213d8ce20852d3', 'convovault/providers/portable.py': '089fef89b1dcc6229f17d20e8fd20ba9a35b435ef1141b4b1c23590b8daac3e7', 'convovault/rendering/conversation.py': '1f4f0b90e2637e0b89d336fe1cbd58f0d6e1825da7212f9756c7edfdad13bfdc', 'convovault/workspace.py': '1a6eef4984abb8d036a7eb3be9fe8b6b5f7f129bee62d7e38d8162c9d7e04633', 'docs/SOURCE-FORMATS.md': '42ae517529cfc262b997b4c547a3df1a5e6b1b9b01ceb48140b837504cf94788', 'docs/USER-GUIDE.md': '836f1d22e269b9127f48c4794faacc71403848210917c693ed2d4f0c27267804', 'docs/VERIFICATION.md': 'c0adbd128262f19ccb8e46432d90cf788e1674ada14e158a639dd440deeff16d', 'docs/images/banner.svg': 'ff3e76291f1479b73ccbf965bfd04bf27b29dff7c2de64a95f7b0754f9ca0fcc', 'docs/images/studio.png': '6ab52c2a07ea9901e37b9fdc5f8d32d3211ea9e30a315436d428ac8beaa71edc', 'docs/index.md': 'a55886115ef3ff34ffa4ad974b5d44298495602d0c74d741af73f27418d2ecb9', 'examples/studio-demo.json': '7a9438433107b8fc5a1d2c3c09d109f6cc0017bf68576190848bfb3e97cc2797', 'launch_studio.py': 'a67f9e73b02eefabf3d5ba5c5dc0974715155d6f7ef9a3d6e8c2b2c5d5c18941', 'pyproject.toml': 'fb3e8a6888eec0839b0dfd7bd3ee4508323655cfebfd0e82cbfa6d848a0558fc', 'requirements.txt': '46094aff51c37755e405e135deebe852a6802787ab6c85bc2fea62279ebe8ecb', 'run_tests.py': '41c2ef237a7a6202740f0ca0fb3c1b0ebf9d1966932feec90e2781af7986c22b', 'scripts/build-windows.ps1': '8514ee2fec6aa39081f2e9674ca6c4c0f56714a1e1de93c7a7318266aaaaed85', 'scripts/verify-release.py': '0a5e6e5a4bf7f02db4b5d9a0dd95fb5535710ff338e018bd5f0543875ee620aa', 'tests/test_studio.py': 'd5be8480d2d912ebf44a361e117ff5e86078ed0b33fabad6febef09b731c3b3f'}

# Each tuple is an independently named commit. Partial module snapshots are staged
# directly in Git's index, so the complete reviewed working files remain intact.
PLAN = [
    ("chore(git): exclude Studio build tools and private verification workspaces", [".gitignore"], None),
    ("feat(import): add read-only portable conversation normalization", ["convovault/providers/portable.py"], None),
    ("fix(chatgpt): import export ZIPs and preserve the selected conversation branch", ["convovault/providers/chatgpt/chatgpt.py", "convovault/providers/chatgpt/provider.py"], None),
    ("fix(claude): normalize exported messages and tool-use blocks", ["convovault/providers/claude/claude_ai.py", "convovault/providers/claude/provider.py"], None),
    ("feat(gemini): replace the placeholder with Gemini CLI session imports", ["convovault/providers/gemini/provider.py"], None),
    ("feat(librechat): enable portable conversation JSON imports", ["convovault/providers/librechat/provider.py"], None),
    ("feat(codex): register local rollout and archived-session imports", ["convovault/providers/plugin_loader.py"], "codex"),
    ("feat(claude-code): register project JSONL transcript imports", ["convovault/providers/plugin_loader.py"], "claude-code"),
    ("feat(import): register generic role-content JSON exports", ["convovault/providers/plugin_loader.py"], "all-providers"),
    ("fix(ollama): supply provider identities when constructing conversations", ["convovault/providers/ollama/ollama.py"], None),
    ("fix(openwebui): construct valid conversations from read-only SQLite", ["convovault/providers/openwebui/ollama.py"], None),
    ("feat(discovery): detect common local assistant transcript paths", ["convovault/discovery.py"], None),
    ("feat(classification): add explainable English and Arabic category rules", ["convovault/analysis/classification.py"], None),
    ("feat(vault): add managed manifests and preservation of edited files", ["convovault/workspace.py"], 9),
    ("feat(notes): add whole-chat exchange and individual-message rendering", ["convovault/workspace.py", "convovault/config/exporter.py"], 16),
    ("feat(graph): add colored brain and topic Canvas layouts", ["convovault/workspace.py"], 17),
    ("feat(vault): merge classified chats with linked parts and topic hubs", ["convovault/workspace.py"], 18),
    ("feat(search): search full Markdown content and linked part notes", ["convovault/workspace.py"], 19),
    ("fix(render): preserve full tool arguments and show the actual provider", ["convovault/rendering/conversation.py"], None),
    ("style(analysis): satisfy arithmetic-spacing lint checks", ["convovault/analysis/intelligence.py"], None),
    ("refactor(export): route synchronization through the safe multi-source library", ["convovault/exporter/engine.py"], None),
    ("feat(studio): add authenticated local API previews and background sync jobs", ["convovault/gui/__init__.py", "convovault/gui/server.py"], None),
    ("feat(gui): add responsive Studio library rules editor and neural map", ["convovault/gui/static/index.html", "convovault/gui/static/style.css", "convovault/gui/static/app.js"], None),
    ("feat(cli): expose Studio discovery search and provider-specific defaults", ["convovault/cli/main.py"], None),
    ("build(python): package Studio assets and release version 3.0.0", ["pyproject.toml", "convovault/__init__.py", "requirements.txt"], None),
    ("feat(windows): add portable Studio launcher and executable build script", ["launch_studio.py", "Start-Studio.cmd", "scripts/build-windows.ps1"], None),
    ("test(studio): cover imports safe exports paths classification and sync", ["tests/test_studio.py", "run_tests.py"], None),
    ("test(release): smoke-test installed wheels and the Windows executable", ["scripts/verify-release.py"], None),
    ("docs(studio): document source formats setup safety and sample data", ["docs/USER-GUIDE.md", "docs/SOURCE-FORMATS.md", "docs/index.md", "examples/studio-demo.json"], None),
    ("docs(verification): record local tests and real Codex validation boundaries", ["docs/VERIFICATION.md"], None),
    ("docs(readme): showcase Studio with screenshots badges and knowledge diagrams", ["README.md", "docs/images/banner.svg", "docs/images/studio.png"], None),
    ("docs(release): describe Studio 3.0 changes and non-destructive migration", ["CHANGELOG.md", "MIGRATION.md"], None),
    ("chore(release): add the guarded single-run feature commit publisher", [SELF], None),
]


def command(args, *, input_bytes=None, capture=True, check=True):
    environment = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never"}
    return subprocess.run(args, cwd=ROOT, env=environment, input=input_bytes,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE if capture else None, check=check)


def git(*args):
    return command(["git", *args]).stdout.decode("utf-8").strip()


def file_hash(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def check_files():
    for path, expected in EXPECTED.items():
        if not (ROOT / path).is_file() or file_hash(path) != expected:
            raise RuntimeError("Reviewed file changed or missing: " + path)


def remote_head():
    line = git("ls-remote", "origin", "refs/heads/" + BRANCH)
    if not line:
        raise RuntimeError("Remote branch was not found")
    return line.split()[0]


def workspace_snapshot(final, count):
    text = final.decode("utf-8")
    functions = [n for n in ast.parse(text).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if len(functions) != 19:
        raise RuntimeError("The reviewed workspace function layout changed")
    if count == len(functions):
        return final
    lines = text.splitlines(keepends=True)
    for node in reversed(functions[count:]):
        first = min([node.lineno] + [d.lineno for d in node.decorator_list])
        del lines[first - 1:node.end_lineno]
    snapshot = "".join(lines)
    ast.parse(snapshot)
    return snapshot.encode("utf-8")


def stage(path, variant, final):
    content = final[path]
    if path == "convovault/workspace.py":
        content = workspace_snapshot(content, variant)
    elif path == "convovault/providers/plugin_loader.py" and variant != "all-providers":
        original = b'for _name in ("chatgpt", "claude", "codex", "claude-code", "gemini", "librechat", "generic"):'
        replacement = b'for _name in ("codex",):' if variant == "codex" else b'for _name in ("codex", "claude-code"):'
        if content.count(original) != 1:
            raise RuntimeError("The reviewed provider registry changed")
        content = content.replace(original, replacement)
    # Validate every staged Python snapshot without replacing working files.
    if path.endswith(".py"):
        compile(content, path, "exec")
    previous = git("ls-tree", "HEAD", "--", path)
    mode = previous.split()[0] if previous else "100644"
    oid = command(["git", "hash-object", "-w", "--stdin"], input_bytes=content).stdout.decode().strip()
    git("update-index", "--add", "--cacheinfo", mode, oid, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Create the reviewed feature commits")
    parser.add_argument("--push", action="store_true", help="Push after all checks and commits succeed")
    args = parser.parse_args()
    if args.push and not args.apply:
        parser.error("--push requires --apply")
    print(f"Reviewed plan: {len(PLAN)} commits on {BRANCH}, base {BASE[:12]}", flush=True)
    for i, (message, paths, _) in enumerate(PLAN, 1):
        print(f"  {i:02}. {message}")
    if not args.apply:
        print("Plan only. Run this file once with --apply --push to publish.")
        return
    if git("rev-parse", "--show-toplevel").replace("\\", "/").lower() != str(ROOT).replace("\\", "/").lower():
        raise RuntimeError("Run inside the intended repository")
    if git("branch", "--show-current") != BRANCH or git("rev-parse", "HEAD") != BASE:
        raise RuntimeError("Unexpected branch/base; this one-time batch must not be applied again")
    if git("remote", "get-url", "origin") != REMOTE:
        raise RuntimeError("Unexpected remote repository")
    if command(["git", "diff", "--cached", "--quiet"], check=False).returncode:
        raise RuntimeError("Pre-existing staged changes must be reviewed separately")
    expected_paths = set(EXPECTED) | {SELF}
    planned_paths = {path for _, paths, _ in PLAN for path in paths}
    if planned_paths != expected_paths:
        raise RuntimeError("Commit plan does not cover exactly the reviewed file set")
    changed = set(filter(None, command(["git", "ls-files", "--modified", "--deleted", "--others", "--exclude-standard", "-z"]).stdout.decode().split("\0")))
    if changed != expected_paths:
        raise RuntimeError("Unexpected/unreviewed working changes: " + repr(sorted(changed ^ expected_paths)))
    for path in expected_paths:
        if command(["git", "check-ignore", "--quiet", "--", path], check=False).returncode == 0:
            raise RuntimeError("Plan includes an ignored/generated/private file: " + path)
    check_files()
    if remote_head() != BASE:
        raise RuntimeError("Remote main advanced; reconcile it before publishing")
    final = {path: (ROOT / path).read_bytes() for path in expected_paths}
    print("Checking the complete reviewed working tree before creating commits...", flush=True)
    command([sys.executable, "run_tests.py"], capture=False)
    command([sys.executable, "-m", "compileall", "-q", "convovault"], capture=False)
    if importlib.util.find_spec("flake8"):
        command([sys.executable, "-m", "flake8", "convovault/", "--max-line-length=120",
                 "--ignore=E501,W503,E203,E701,E702,E241,E261,E272,E221,E305,W504", "--exclude=__pycache__"], capture=False)
    else:
        print("flake8 is not installed; the test and compilation gates still ran.")
    check_files()
    journal_path = ROOT / ".git" / "convovault-publish-journal.json"
    journal = {"base": BASE, "branch": BRANCH, "started_at": datetime.now(timezone.utc).isoformat(), "commits": [], "pushed": False}

    def save_journal():
        temporary = journal_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(journal, indent=2) + "\n", encoding="utf-8")
        temporary.replace(journal_path)

    save_journal()
    for i, (message, paths, variant) in enumerate(PLAN, 1):
        print(f"Committing {i}/{len(PLAN)}: {message}", flush=True)
        for path in paths:
            stage(path, variant, final)
        if command(["git", "diff", "--cached", "--quiet"], check=False).returncode == 0:
            raise RuntimeError("Empty feature commit refused: " + message)
        command(["git", "commit", "-m", message], capture=False)
        journal["commits"].append({"sha": git("rev-parse", "HEAD"), "message": message, "paths": paths})
        save_journal()
    check_files()
    if git("status", "--porcelain"):
        raise RuntimeError("Working tree is not clean after the batch; nothing was pushed")
    if int(git("rev-list", "--count", BASE + "..HEAD")) != len(PLAN):
        raise RuntimeError("Unexpected commit count")
    if args.push:
        if remote_head() != BASE:
            raise RuntimeError("Remote advanced during the batch; local commits were retained, with no force push")
        command(["git", "push", "origin", "HEAD:refs/heads/" + BRANCH], capture=False)
        if remote_head() != git("rev-parse", "HEAD"):
            raise RuntimeError("Remote verification did not match the local commit")
        git("fetch", "--quiet", "origin", BRANCH)
        journal["pushed"] = True
        save_journal()
    print(f"Done: {len(journal['commits'])} commits; pushed={journal['pushed']}; HEAD={git('rev-parse', 'HEAD')}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        if exc.stderr:
            print(exc.stderr.decode("utf-8", errors="replace"), file=sys.stderr)
        raise SystemExit("Batch stopped. Existing commits are retained; no history was reset or force-pushed.")
    except Exception as exc:
        raise SystemExit(f"Batch stopped: {exc}")
