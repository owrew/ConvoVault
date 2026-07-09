"""
test_markdown.py
================
Tests formatting steps, YAML frontmatter tags, turns output format.
"""
from __future__ import annotations
from agy_exporter.models import Step, ConversationTranscript, ConversationMeta
from agy_exporter.render.conversation import format_conversation
from agy_exporter.analysis.intelligence import generate_intelligence

def _make_transcript(steps=None, conv_id="convo_123"):
    ts = ConversationTranscript(
        conv_id=conv_id,
        steps=steps or [],
        source_file="mock.jsonl"
    )
    ts.intelligence = generate_intelligence(ts)
    return ts

def test_format_conversation():
    steps = [
        Step(
            index=0,
            source="USER_EXPLICIT",
            step_type="USER_INPUT",
            status="DONE",
            created_at="2026-06-18T14:38:27Z",
            content="Hello assistant."
        )
    ]
    ts = _make_transcript(steps)
    meta = ConversationMeta(conversation_id="convo_123", title="Test Title")
    md = format_conversation(ts, meta, all_meta={"convo_123": meta})

    assert 'title: "Test Title"' in md
    assert 'id: "convo_123"' in md
    assert "# Test Title" in md
    assert "User — Turn 1" in md
    assert "Hello assistant." in md
    # New sections
    assert "Conversation Statistics" in md
    assert "user_turns:" in md

def test_format_conversation_strips_system_metadata():
    """ADDITIONAL_METADATA must not appear in the rendered note."""
    raw = (
        "<USER_REQUEST>Fix the bug.</USER_REQUEST>\n"
        "<ADDITIONAL_METADATA>OS: windows</ADDITIONAL_METADATA>"
    )
    steps = [
        Step(index=0, source="USER_EXPLICIT", step_type="USER_INPUT",
             status="DONE", created_at="2026-06-18T14:38:27Z", content=raw)
    ]
    ts = _make_transcript(steps)
    meta = ConversationMeta(conversation_id="convo_123", title="Bug Fix")
    md = format_conversation(ts, meta, all_meta={"convo_123": meta})

    assert "Fix the bug." in md
    assert "OS: windows" not in md
    assert "ADDITIONAL_METADATA" not in md

def test_format_conversation_thinking_blocks():
    """Thinking blocks are rendered in collapsible <details> sections."""
    steps = [
        Step(index=0, source="USER_EXPLICIT", step_type="USER_INPUT",
             status="DONE", created_at="2026-06-18T14:38:00Z", content="Explain X"),
        Step(index=1, source="MODEL", step_type="PLANNER_RESPONSE",
             status="DONE", created_at="2026-06-18T14:38:10Z",
             content="X is a concept.", thinking="Let me think through this carefully.")
    ]
    ts = _make_transcript(steps)
    meta = ConversationMeta(conversation_id="convo_123", title="Thinking Test")
    md = format_conversation(ts, meta, all_meta={"convo_123": meta})

    assert "💭 Thinking Process" in md
    assert "Let me think through this carefully." in md
    assert "X is a concept." in md

def test_format_conversation_all_sections_present():
    """All required sections must appear in a populated conversation."""
    steps = [
        Step(index=0, source="USER_EXPLICIT", step_type="USER_INPUT",
             status="DONE", created_at="2026-06-18T14:00:00Z", content="Start"),
    ]
    ts = _make_transcript(steps)
    meta = ConversationMeta(conversation_id="convo_123", title="Sections Test")
    md = format_conversation(ts, meta, all_meta={"convo_123": meta})

    for section in [
        "Conversation Statistics",
        "Conversation History",
        "Conversation Intelligence",
    ]:
        assert section in md, f"Missing section: {section}"
