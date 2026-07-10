"""
annotations.py
==============
Parser for Antigravity annotations pbtxt files.
"""
from __future__ import annotations
import os
import re
import logging
from typing import Optional

log = logging.getLogger(__name__)

def parse_annotation(pbtxt_path: str) -> Optional[int]:
    """
    Parse last_user_view_time from annotations/{conv_id}.pbtxt.
    Format: last_user_view_time:{seconds:1781815877  nanos:125000000}
    """
    if not os.path.isfile(pbtxt_path):
        return None
    try:
        with open(pbtxt_path, 'r', encoding='utf-8') as fh:
            text = fh.read()
        m = re.search(r'last_user_view_time\s*:\s*\{\s*seconds\s*:\s*(\d+)', text)
        if m:
            return int(m.group(1))
    except Exception as e:
        log.debug("Could not parse annotation %s: %s", pbtxt_path, e)
    return None
