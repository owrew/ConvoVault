"""
mermaid.py
==========
Generates Mermaid mindmap or flowcharts displaying the technologies used in a conversation.
"""
from __future__ import annotations
from typing import List

def generate_mermaid_diagram(title: str, technologies: List[str]) -> str:
    """
    Returns a valid quoted Mermaid flowchart TD codeblock.
    """
    if not technologies:
        return ""
    
    # Safe quoting for title
    safe_title = title.replace('"', '\\"').strip()
    
    lines = []
    lines.append("```mermaid")
    lines.append("flowchart TD")
    lines.append(f'  Root["{safe_title}"]')
    
    for i, tech in enumerate(technologies):
        safe_tech = tech.replace('"', '\\"').strip()
        lines.append(f'  Tech{i}["{safe_tech}"]')
        lines.append(f'  Root --> Tech{i}')
        
    lines.append("```")
    return "\n".join(lines)
