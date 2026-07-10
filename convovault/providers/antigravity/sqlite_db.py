"""
sqlite_db.py
============
Fallback SQLite database step retriever using raw protobuf decoding.
"""
from __future__ import annotations
import logging
import os
import sqlite3
import struct
from typing import Iterator, List, Optional, Tuple
from ...models import Step, ConversationTranscript

log = logging.getLogger(__name__)

def _read_varint(buf: bytes, pos: int) -> Tuple[int, int]:
    result, shift = 0, 0
    while pos < len(buf):
        b = buf[pos]; pos += 1
        result |= (b & 0x7F) << shift
        shift += 7
        if not (b & 0x80):
            break
    return result, pos

def _decode_fields(data: bytes):
    buf = bytes(data)
    pos, out, errors = 0, [], 0
    while pos < len(buf) and errors < 5:
        try:
            if pos >= len(buf):
                break
            tag, pos = _read_varint(buf, pos)
            if tag == 0:
                break
            fn = tag >> 3
            wt = tag & 0x7
            if wt == 0:
                v, pos = _read_varint(buf, pos)
                out.append((fn, 0, v))
            elif wt == 1:
                if pos + 8 > len(buf):
                    break
                v = struct.unpack_from('<Q', buf, pos)[0]
                pos += 8
                out.append((fn, 1, v))
            elif wt == 2:
                length, pos = _read_varint(buf, pos)
                if pos + length > len(buf) or length > 20_000_000:
                    errors += 1
                    break
                v = buf[pos:pos + length]
                pos += length
                out.append((fn, 2, v))
            elif wt == 5:
                if pos + 4 > len(buf):
                    break
                v = struct.unpack_from('<I', buf, pos)[0]
                pos += 4
                out.append((fn, 5, v))
            else:
                errors += 1
        except Exception:
            errors += 1
    return out

def _try_str(v: bytes) -> Optional[str]:
    if isinstance(v, bytes):
        try:
            s = v.decode('utf-8')
            if len(s) > 0 and sum(1 for c in s if c.isprintable() or c in '\n\r\t') / len(s) > 0.85:
                return s
        except Exception:
            pass
    return None

def _decode_timestamp_pb(raw: bytes) -> int:
    for fn, wt, v in _decode_fields(raw):
        if fn == 1 and wt == 0:
            return v
    return 0

def _seconds_to_iso(sec: int) -> str:
    from datetime import datetime, timezone
    try:
        return datetime.fromtimestamp(sec, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    except Exception:
        return ""

_STEP_TYPE_MAP = {
    14: "USER_INPUT",
    15: "PLANNER_RESPONSE",
    8:  "VIEW_FILE",
    9:  "LIST_DIRECTORY",
    17: "ERROR",
    23: "SUBAGENT_INVOKE",
    132: "SEND_MESSAGE",
}

def _extract_text_from_payload(payload: bytes) -> str:
    fields = _decode_fields(payload)
    texts = []
    for fn, wt, v in fields:
        if wt != 2 or not isinstance(v, bytes):
            continue
        s = _try_str(v)
        if s and fn in (14, 15, 20, 30, 140) and len(s) > 20:
            sub_fields = _decode_fields(v)
            inner_text = None
            for sfn, swt, sv in sub_fields:
                if sfn == 1 and swt == 2:
                    inner_text = _try_str(sv)
                    if inner_text and len(inner_text) > 10:
                        break
            texts.append(inner_text or s)
    return '\n\n'.join(t for t in texts if t)

def read_from_sqlite(db_path: str, conv_id: str) -> Optional[ConversationTranscript]:
    if not os.path.isfile(db_path):
        return None

    try:
        conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
    except Exception as e:
        log.warning("Cannot open database %s: %s", db_path, e)
        return None

    try:
        cur.execute('''
            SELECT idx, step_type, status, metadata, step_payload
            FROM steps
            ORDER BY idx
        ''')
        rows = cur.fetchall()
    except Exception as e:
        log.warning("Cannot query steps table in %s: %s", db_path, e)
        conn.close()
        return None
    finally:
        conn.close()

    steps: List[Step] = []
    for row in rows:
        idx = row['idx']
        step_type_int = row['step_type'] or 0
        status_int = row['status'] or 0
        metadata_raw = row['metadata']
        payload_raw = row['step_payload']

        step_type_str = _STEP_TYPE_MAP.get(step_type_int, f"UNKNOWN_{step_type_int}")

        created_at = ""
        if metadata_raw:
            try:
                meta_fields = _decode_fields(bytes(metadata_raw))
                for fn, wt, v in meta_fields:
                    if fn == 1 and wt == 2:
                        sec = _decode_timestamp_pb(bytes(v))
                        if sec > 0:
                            created_at = _seconds_to_iso(sec)
                        break
            except Exception:
                pass

        content = ""
        if payload_raw:
            try:
                content = _extract_text_from_payload(bytes(payload_raw))
            except Exception as e:
                log.debug("Payload decode error step idx %d: %s", idx, e)
                content = f"[raw protobuf payload: decode failed]"

        steps.append(Step(
            index=idx,
            source="MODEL" if step_type_str == "PLANNER_RESPONSE" else "USER_EXPLICIT",
            step_type=step_type_str,
            status="DONE" if status_int == 3 else str(status_int),
            created_at=created_at,
            content=content,
        ))

    if not steps:
        return None

    log.info("Recovered %d steps from SQLite db: %s", len(steps), conv_id)
    return ConversationTranscript(
        conv_id=conv_id,
        steps=steps,
        source_file=db_path,
    )
