"""
wikilinks.py
============
Pattern-based topic classifier extracting Obsidian WikiLinks and tags.
"""
from __future__ import annotations
import re
import logging
from typing import List, Set, Tuple

log = logging.getLogger(__name__)

_TECH_PATTERNS: List[Tuple[str, str, str]] = [
    (r'\bPython\b', 'Python', 'python'),
    (r'\bTypeScript\b', 'TypeScript', 'typescript'),
    (r'\bJavaScript\b', 'JavaScript', 'javascript'),
    (r'\bReact\b', 'React', 'react'),
    (r'\bNext\.js\b|\bNextjs\b', 'Next.js', 'nextjs'),
    (r'\bVite\b', 'Vite', 'vite'),
    (r'\bNode\.js\b|\bNodejs\b|\bNode\b', 'Node.js', 'nodejs'),
    (r'\bRust\b', 'Rust', 'rust'),
    (r'\bGo\b(?!ogle)', 'Go', 'golang'),
    (r'\bJava\b', 'Java', 'java'),
    (r'\bKotlin\b', 'Kotlin', 'kotlin'),
    (r'\bSwift\b', 'Swift', 'swift'),
    (r'\bDart\b', 'Dart', 'dart'),
    (r'\bFlutter\b', 'Flutter', 'flutter'),
    (r'\bReact Native\b', 'React Native', 'react-native'),
    (r'\bExpo\b', 'Expo', 'expo'),
    (r'\bPostgreSQL\b|\bPostgres\b', 'PostgreSQL', 'postgresql'),
    (r'\bMySQL\b', 'MySQL', 'mysql'),
    (r'\bSQLite\b', 'SQLite', 'sqlite'),
    (r'\bMongoDB\b', 'MongoDB', 'mongodb'),
    (r'\bRedis\b', 'Redis', 'redis'),
    (r'\bFirebase\b', 'Firebase', 'firebase'),
    (r'\bSupabase\b', 'Supabase', 'supabase'),
    (r'\bDrizzle(?:\s+ORM)?\b', 'Drizzle ORM', 'drizzle-orm'),
    (r'\bPrisma\b', 'Prisma', 'prisma'),
    (r'\bDocker\b', 'Docker', 'docker'),
    (r'\bKubernetes\b|\bk8s\b', 'Kubernetes', 'kubernetes'),
    (r'\bRailway\b', 'Railway', 'railway'),
    (r'\bVercel\b', 'Vercel', 'vercel'),
    (r'\bAWS\b', 'AWS', 'aws'),
    (r'\bGoogle Cloud\b|\bGCP\b', 'Google Cloud', 'gcp'),
    (r'\bAzure\b', 'Azure', 'azure'),
    (r'\bGitHub\b', 'GitHub', 'github'),
    (r'\bGit\b', 'Git', 'git'),
    (r'\bCI/CD\b', 'CI/CD', 'cicd'),
    (r'\bREST(?:\s+API)?\b', 'REST API', 'rest-api'),
    (r'\btRPC\b', 'tRPC', 'trpc'),
    (r'\bGraphQL\b', 'GraphQL', 'graphql'),
    (r'\bOAuth\b', 'OAuth', 'oauth'),
    (r'\bJWT\b', 'JWT', 'jwt'),
    (r'\bAuth(?:entication|orization)?\b', 'Authentication', 'auth'),
    (r'\bRBAC\b', 'RBAC', 'rbac'),
    (r'\bClaude\b', 'Claude', 'claude'),
    (r'\bGemini\b', 'Gemini', 'gemini'),
    (r'\bOpenAI\b|\bChatGPT\b|\bGPT-?\d?\b', 'OpenAI', 'openai'),
    (r'\bCodex\b', 'Codex', 'codex'),
    (r'\bQwen\b', 'Qwen', 'qwen'),
    (r'\bZ\s*AI\b|\bZAI\b', 'Z AI', 'z-ai'),
    (r'\bOllama\b', 'Ollama', 'ollama'),
    (r'\bDeepSeek\b', 'DeepSeek', 'deepseek'),
    (r'\bLlama\b', 'Llama', 'llama'),
    (r'\bMistral\b', 'Mistral', 'mistral'),
    (r'\bGemma\b', 'Gemma', 'gemma'),
    (r'\blocal\s*AI\b', 'Local AI', 'local-ai'),
    (r'\bLLM\b', 'LLM', 'llm'),
    (r'\bMachine Learning\b|\bML\b', 'Machine Learning', 'machine-learning'),
    (r'\bXSS\b', 'XSS', 'xss'),
    (r'\bSQL Injection\b|\bSQLi\b', 'SQL Injection', 'sqli'),
    (r'\bBug Bounty\b', 'Bug Bounty', 'bug-bounty'),
    (r'\bPenetration Testing\b|\bPen Test\b', 'Penetration Testing', 'pentest'),
    (r'\bBurp Suite\b', 'Burp Suite', 'burpsuite'),
    (r'\bRecon\b|\bReconnaissance\b', 'Recon', 'recon'),
    (r'\bObsidian\b', 'Obsidian', 'obsidian'),
    (r'\bVS Code\b|\bVSCode\b', 'VS Code', 'vscode'),
    (r'\bTailwind(?:\s+CSS)?\b', 'Tailwind CSS', 'tailwindcss'),
    (r'\bCSS\b', 'CSS', 'css'),
    (r'\bHTML\b', 'HTML', 'html'),
    (r'\bMarkdown\b', 'Markdown', 'markdown'),
    (r'\bPDF\b', 'PDF', 'pdf'),
    (r'\bWebSocket\b', 'WebSocket', 'websocket'),
    (r'\bprotobuf\b|\bProtocol Buffers\b', 'Protobuf', 'protobuf'),
    (r'\bAndroid\b', 'Android', 'android'),
    (r'\biOS\b', 'iOS', 'ios'),
    (r'\bExpress\b', 'Express.js', 'expressjs'),
    (r'\bFastAPI\b', 'FastAPI', 'fastapi'),
    (r'\bDjango\b', 'Django', 'django'),
    (r'\bpnpm\b|\bnpm\b|\byarn\b', 'Package Manager', 'npm'),
    (r'\bEAS\b|\bEAS CLI\b', 'EAS CLI', 'eas'),
    (r'\bPuppeteer\b', 'Puppeteer', 'puppeteer'),
    (r'\bRTL\b', 'RTL', 'rtl'),
    (r'\bArabic\b', 'Arabic', 'arabic'),
]

_COMPILED = [(re.compile(pat, re.IGNORECASE), name, tag) for pat, name, tag in _TECH_PATTERNS]
_BASE_TAGS = ['convovault', 'ai-chat']

def extract_topics(text: str) -> Tuple[List[str], List[str]]:
    seen_names: Set[str] = set()
    seen_tags: Set[str] = set()
    wiki_links: List[str] = []
    tags: List[str] = list(_BASE_TAGS)

    for pattern, canonical, tag in _COMPILED:
        if pattern.search(text):
            if canonical not in seen_names:
                seen_names.add(canonical)
                wiki_links.append(canonical)
            if tag not in seen_tags:
                seen_tags.add(tag)
                tags.append(tag)

    seen_tags_set = set(_BASE_TAGS)
    final_tags = list(_BASE_TAGS)
    for t in tags:
        if t not in seen_tags_set:
            seen_tags_set.add(t)
            final_tags.append(t)

    return wiki_links, final_tags

def slugify(text: str) -> str:
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text.strip())
    text = re.sub(r'-+', '-', text)
    return text[:80].strip('-')

def title_to_filename(title: str) -> str:
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', title)
    safe = safe.strip().strip('.')
    if not safe:
        safe = 'Untitled'
    if len(safe) > 100:
        safe = safe[:97] + '...'
    return safe + '.md'
