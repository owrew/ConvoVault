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
    raw_user = (
        "<USER_REQUEST>\n"
        "Please fix this styling issue.\n"
        "</USER_REQUEST>\n"
        "<ADDITIONAL_METADATA>\n"
        "OS: windows\n"
        "</ADDITIONAL_METADATA>"
    )
    cleaned = clean_user_content(raw_user)
    assert "Please fix this styling issue." in cleaned
    assert "OS: windows" in cleaned

def test_clean_user_content_no_tags():
    raw_user = "A normal direct message without tags."
    cleaned = clean_user_content(raw_user)
    assert cleaned == "A normal direct message without tags."
