"""Explainable multilingual keyword classification; no probabilistic claims."""
import re

DEFAULT_RULES = [
    {"name": "Development", "color": "#769dff", "keywords": ["python", "typescript", "javascript", "code", "debug", "api", "database", "برمجة", "كود", "خوارزمية"]},
    {"name": "Study", "color": "#e6b65b", "keywords": ["exam", "assignment", "calculus", "lecture", "homework", "university", "دراسة", "امتحان", "رياضيات", "واجب", "جامعة"]},
    {"name": "Research", "color": "#bd8ee8", "keywords": ["research", "citation", "sources", "paper", "evidence", "بحث", "مصادر", "الشاملة", "الرفاعية", "مرجع"]},
    {"name": "Writing", "color": "#df879b", "keywords": ["email", "essay", "rewrite", "translate", "draft", "رسالة", "ترجمة", "صياغة", "مقال"]},
    {"name": "Projects", "color": "#58bbad", "keywords": ["project", "roadmap", "product", "design", "business", "مشروع", "تصميم", "خطة"]},
    {"name": "Everyday", "color": "#94acbd", "keywords": ["recipe", "travel", "schedule", "shopping", "سفر", "وصفة", "جدول"]},
]


def validate_rules(rules):
    if not isinstance(rules, list) or len(rules) > 50:
        raise ValueError("Rules must be a list of at most 50 categories")
    names = set()
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get("name"), str) or not rule["name"].strip():
            raise ValueError("Every category needs a name")
        if len(rule["name"]) > 60 or rule["name"] in names:
            raise ValueError("Category names must be unique and at most 60 characters")
        names.add(rule["name"])
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", rule.get("color", "")):
            raise ValueError("Use a six-digit hex color such as #769dff")
        keywords = rule.get("keywords")
        if not isinstance(keywords, list) or len(keywords) > 100 or any(not isinstance(k, str) or not k.strip() or len(k) > 100 for k in keywords):
            raise ValueError("Keywords must be a list of up to 100 nonempty phrases")
    return rules


def classify(text, rules=None, override=None):
    rules = DEFAULT_RULES if rules is None else rules
    scores, evidence = {}, {}
    for rule in rules:
        hits = [k for k in rule["keywords"] if re.search(r"(?<!\w)" + re.escape(k) + r"(?!\w)", text, re.I)]
        if hits:
            scores[rule["name"]] = len(hits)
            evidence[rule["name"]] = hits
    categories = sorted(scores, key=lambda k: -scores[k])
    primary = override or (categories[0] if categories else "Unsorted")
    color = next((r["color"] for r in rules if r["name"] == primary), "#94acbd")
    return {"primary": primary, "categories": list(dict.fromkeys([primary] + categories)),
            "evidence": evidence, "scores": scores, "color": color,
            "method": "manual" if override else "keyword rules"}
