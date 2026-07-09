"""
test_transcript.py
==================
Tests transcript JSONL reader and user content cleaning logic.
"""
from __future__ import annotations
import tempfile
import os
from agy_exporter.sources.transcript import clean_user_content, _iter_steps

def test_clean_user_content():
    """USER_REQUEST content is kept; ADDITIONAL_METADATA block is stripped entirely."""
    raw_user = (
        "<USER_REQUEST>\n"
        "Please fix this styling issue.\n"
        "</USER_REQUEST>\n"
        "<ADDITIONAL_METADATA>\n"
        "OS: windows\n"
        "</ADDITIONAL_METADATA>"
    )
    cleaned = clean_user_content(raw_user)
    # The user's request text must survive
    assert "Please fix this styling issue." in cleaned
    # System metadata must be removed completely
    assert "OS: windows" not in cleaned
    assert "<ADDITIONAL_METADATA>" not in cleaned

def test_clean_user_content_no_tags():
    raw_user = "A normal direct message without tags."
    cleaned = clean_user_content(raw_user)
    assert cleaned == "A normal direct message without tags."

def test_clean_user_content_strips_settings_change():
    """USER_SETTINGS_CHANGE blocks are purely system-injected and must be removed."""
    raw_user = (
        "<USER_REQUEST>Fix the bug.</USER_REQUEST>\n"
        "<USER_SETTINGS_CHANGE>\n"
        "Model changed to Claude.\n"
        "</USER_SETTINGS_CHANGE>"
    )
    cleaned = clean_user_content(raw_user)
    assert "Fix the bug." in cleaned
    assert "Model changed" not in cleaned

def test_clean_user_content_preserves_inner_xml():
    """XML inside the user's actual request text must not be stripped."""
    raw_user = (
        "<USER_REQUEST>\n"
        "Use this config: <config>debug=true</config>\n"
        "</USER_REQUEST>"
    )
    cleaned = clean_user_content(raw_user)
    assert "<config>debug=true</config>" in cleaned
