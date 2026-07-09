"""
intelligence.py
===============
Analyzes conversation transcripts to generate a summary, list topics,
technologies, files mentioned, commands executed, and code languages used.
"""
from __future__ import annotations
import os
import re
from typing import List, Set, Tuple, Any
from ..models import Step, ConversationTranscript, ConversationIntelligence
from ..sources.transcript import TOOL_RESULT_TYPES

# Pattern dictionaries for tech & topics detection
_TECH_STACK = {
    "React": r"\bReact\b",
    "TypeScript": r"\bTypeScript\b|\bts\b",
    "JavaScript": r"\bJavaScript\b|\bjs\b",
    "Next.js": r"\bNext\.js\b|\bNextjs\b",
    "Vite": r"\bVite\b",
    "Node.js": r"\bNode\.js\b|\bNodejs\b|\bNode\b",
    "Rust": r"\bRust\b",
    "Go": r"\bGo\b(?!ogle)",
    "Java": r"\bJava\b",
    "Python": r"\bPython\b",
    "Ruby": r"\bRuby\b",
    "PHP": r"\bPHP\b",
    "HTML": r"\bHTML\b",
    "CSS": r"\bCSS\b",
    "SQL": r"\bSQL\b",
    "MySQL": r"\bMySQL\b",
    "PostgreSQL": r"\bPostgreSQL\b|\bPostgres\b",
    "SQLite": r"\bSQLite\b",
    "MongoDB": r"\bMongoDB\b",
    "Redis": r"\bRedis\b",
    "Docker": r"\bDocker\b",
    "Kubernetes": r"\bKubernetes\b|\bk8s\b",
    "Railway": r"\bRailway\b",
    "Vercel": r"\bVercel\b",
    "AWS": r"\bAWS\b|\bAmazon Web Services\b",
    "Google Cloud": r"\bGCP\b|\bGoogle Cloud\b",
    "Firebase": r"\bFirebase\b",
    "Supabase": r"\bSupabase\b",
    "Drizzle ORM": r"\bDrizzle\b",
    "Prisma": r"\bPrisma\b",
    "tRPC": r"\btRPC\b",
    "GraphQL": r"\bGraphQL\b",
    "REST API": r"\bREST\b",
    "Tailwind CSS": r"\bTailwind\b",
    "Puppeteer": r"\bPuppeteer\b",
    "Android": r"\bAndroid\b",
    "iOS": r"\biOS\b",
    "Expo": r"\bExpo\b",
    "React Native": r"\bReact Native\b",
    "Zod": r"\bZod\b",
    "Webpack": r"\bWebpack\b",
    "EAS CLI": r"\bEAS CLI\b|\bEAS\b",
    "Express.js": r"\bExpress\b",
    "FastAPI": r"\bFastAPI\b",
    "Django": r"\bDjango\b",
    "Claude": r"\bClaude\b",
    "Codex": r"\bCodex\b",
    "Qwen": r"\bQwen\b",
    "Z AI": r"\bZ\s*AI\b|\bZAI\b",
    "Ollama": r"\bOllama\b",
    "DeepSeek": r"\bDeepSeek\b",
    "Llama": r"\bLlama\b",
    "Mistral": r"\bMistral\b",
    "Gemma": r"\bGemma\b",
    "Local AI": r"\blocal\s*AI\b",
}

_TOPIC_PATTERNS = {
    "Database Migration": r"\bmigration\b|\bseed\b|\bupgrades?\b|\bforeign key\b",
    "API Development": r"\bapi\b|\brouter\b|\bendpoint\b|\btRPC\b|\bgraphql\b",
    "Authentication": r"\bauth\b|\blogin\b|\bsignup\b|\bjwt\b|\boauth\b|\bsession\b",
    "Role-Based Access Control": r"\brbac\b|\broles?\b|\bpermissions?\b",
    "Deployment": r"\bdeploy\b|\brailway\b|\bdockerfile\b|\bcontainer\b",
    "Dependency Management": r"\binstall\b|\bpnpm\b|\bnpm\b|\byarn\b|\bpackage\.json\b",
    "Error Fixing": r"\berror\b|\bfix\b|\bbug\b|\bcrash\b|\bissue\b|\bdebug\b",
    "Code Review": r"\binspect\b|\bread\b|\banalyze\b|\breview\b",
    "Mobile App Sync": r"\bmobile\b|\bandroid\b|\bios\b|\bexpo\b|\bsync\b",
    "Search Optimization": r"\bsearch\b|\bseo\b|\bconsole\b|\bverification\b",
}

_FILE_PATH_RE = re.compile(
    r'(?:[a-zA-Z]:\\|[a-zA-Z0-9_\-\.]+/)+'
    r'[a-zA-Z0-9_\-\.]+\.[a-zA-Z0-9]{2,4}\b'
)

def _extract_files(text: str) -> Set[str]:
    files = set()
    for match in _FILE_PATH_RE.finditer(text):
        path = match.group(0)
        # Filter out obvious false positives
        if any(x in path for x in ("http:", "https:", "@", "node_modules", "package-lock")):
            continue
        # Standardize separator
        path = path.replace("\\", "/")
        # Avoid directories or simple extensions
        if "/" in path and not path.endswith((".ts", ".tsx", ".js", ".jsx", ".py", ".rs", ".go", ".sql", ".css", ".html", ".json", ".md", ".yml", ".yaml", ".lock", ".sh", ".bat", ".pbtxt", ".pb")):
            continue
        files.add(os.path.basename(path))
    return files

def _extract_commands(steps: List[Step]) -> List[str]:
    commands = []
    for step in steps:
        # Check command run tool
        for tc in step.tool_calls:
            if tc.name == "run_command":
                cmd = tc.args.get("CommandLine") or tc.args.get("command")
                if cmd:
                    commands.append(str(cmd).strip())
        # Parse command lines from contents (heuristics)
        if step.step_type == "RUN_COMMAND" and step.content:
            pass # tool result
    return commands

def _extract_languages(steps: List[Step]) -> Set[str]:
    langs = set()
    lang_map = {
        "ts": "TypeScript", "tsx": "TypeScript",
        "js": "JavaScript", "jsx": "JavaScript",
        "py": "Python", "rs": "Rust",
        "go": "Go", "sql": "SQL",
        "css": "CSS", "html": "HTML",
        "json": "JSON", "md": "Markdown",
        "yml": "YAML", "yaml": "YAML",
        "sh": "Shell", "bat": "Batch",
        "pbtxt": "Protobuf", "pb": "Protobuf"
    }
    
    # 1. Check codeblocks in markdown
    for step in steps:
        if step.content:
            for match in re.finditer(r"```([a-zA-Z0-9#+-]+)", step.content):
                lang = match.group(1).lower()
                if lang in ("typescript", "ts"): langs.add("TypeScript")
                elif lang in ("javascript", "js"): langs.add("JavaScript")
                elif lang in ("python", "py"): langs.add("Python")
                elif lang == "rust": langs.add("Rust")
                elif lang == "go": langs.add("Go")
                elif lang == "sql": langs.add("SQL")
                elif lang == "css": langs.add("CSS")
                elif lang == "html": langs.add("HTML")
                elif lang == "json": langs.add("JSON")
                elif lang == "markdown": langs.add("Markdown")
                elif lang in ("yaml", "yml"): langs.add("YAML")
                elif lang in ("shell", "sh", "bash"): langs.add("Shell")
                elif lang in ("batch", "bat"): langs.add("Batch")
                elif lang in ("protobuf", "proto"): langs.add("Protobuf")

    # 2. Check file path extensions
    for step in steps:
        for tc in step.tool_calls:
            path = tc.args.get("AbsolutePath") or tc.args.get("TargetFile") or tc.args.get("path")
            if path:
                ext = str(path).split(".")[-1].lower()
                if ext in lang_map:
                    langs.add(lang_map[ext])
    return langs

def _generate_summary(conv_id: str, steps: List[Step]) -> str:
    """
    Generates a detailed, multi-paragraph human-readable conversation summary.
    Includes all user requests, tool usage statistics, and any errors encountered.
    """
    from ..sources.transcript import clean_user_content  # local import to avoid circular

    user_requests: List[str] = []
    tool_actions: List[str] = []
    tool_name_counts: dict = {}
    errors: List[str] = []
    files_written: List[str] = []
    commands_run: List[str] = []

    for step in steps:
        if step.step_type == "USER_INPUT" and step.content:
            clean = clean_user_content(step.content)
            first_line = clean.split('\n')[0].strip()
            if len(first_line) > 6:
                user_requests.append(first_line)

        for tc in step.tool_calls:
            # Track by name for counts
            tool_name_counts[tc.name] = tool_name_counts.get(tc.name, 0) + 1
            summary = tc.tool_summary or tc.tool_action
            if summary:
                tool_actions.append(summary.strip())
            # Track file writes
            if tc.name in ("write_to_file", "replace_file_content", "multi_replace_file_content"):
                path = tc.args.get("TargetFile") or tc.args.get("path", "")
                if path:
                    files_written.append(os.path.basename(str(path)))
            # Track commands run
            if tc.name == "run_command":
                cmd = tc.args.get("CommandLine") or tc.args.get("command", "")
                if cmd:
                    commands_run.append(str(cmd).strip()[:80])

        if step.step_type == "ERROR" and step.content:
            errors.append(step.content.split('\n')[0].strip())

    parts: List[str] = []

    # 1. User requests section
    if user_requests:
        if len(user_requests) == 1:
            req = user_requests[0]
            if not req.endswith(('.', '?', '!')):
                req += '.'
            parts.append(f"**User request:** {req}")
        else:
            req_list = "\n".join(f"  {i+1}. {r}" for i, r in enumerate(user_requests[:10]))
            if len(user_requests) > 10:
                req_list += f"\n  … and {len(user_requests) - 10} more"
            parts.append(f"**User requests ({len(user_requests)} total):**\n{req_list}")

    # 2. Tool usage breakdown
    if tool_name_counts:
        total_calls = sum(tool_name_counts.values())
        top_tools = sorted(tool_name_counts.items(), key=lambda x: -x[1])[:8]
        tool_str = ", ".join(f"`{name}` ×{count}" for name, count in top_tools)
        if len(tool_name_counts) > 8:
            tool_str += f", …+{len(tool_name_counts)-8} more"
        parts.append(f"**Tool calls:** {total_calls} total — {tool_str}")

    # 3. Files written
    if files_written:
        unique_files = list(dict.fromkeys(files_written))[:12]
        parts.append(f"**Files written/edited:** {', '.join(f'`{f}`' for f in unique_files)}")

    # 4. Commands run
    if commands_run:
        unique_cmds = list(dict.fromkeys(commands_run))[:5]
        cmd_preview = "; ".join(f"`{c}`" for c in unique_cmds)
        if len(commands_run) > 5:
            cmd_preview += f" … +{len(commands_run) - 5} more"
        parts.append(f"**Commands executed:** {cmd_preview}")

    # 5. Errors encountered
    if errors:
        err_list = "; ".join(errors[:3])
        if len(errors) > 3:
            err_list += f" … +{len(errors)-3} more"
        parts.append(f"**Issues encountered:** {err_list}")

    if not parts:
        return "No significant actions or messages recorded in this conversation."

    return "\n\n".join(parts)


def generate_intelligence(transcript: ConversationTranscript) -> ConversationIntelligence:
    steps = transcript.steps
    all_text = " ".join([s.content for s in steps if s.content])
    
    # 1. Tech stack
    tech = []
    for name, pat in _TECH_STACK.items():
        if re.search(pat, all_text, re.IGNORECASE):
            tech.append(name)
            
    # 2. Topics
    topics = []
    for name, pat in _TOPIC_PATTERNS.items():
        if re.search(pat, all_text, re.IGNORECASE):
            topics.append(name)
            
    # 3. Files Mentioned
    files = _extract_files(all_text)
    
    # 4. Commands
    commands = _extract_commands(steps)
    
    # 5. Languages
    languages = sorted(list(_extract_languages(steps)))
    
    # 6. Summary
    summary = _generate_summary(transcript.conv_id, steps)
    
    return ConversationIntelligence(
        summary=summary,
        topics=topics,
        technologies=tech,
        files_mentioned=sorted(list(files)),
        commands_executed=commands,
        code_languages=languages
    )
