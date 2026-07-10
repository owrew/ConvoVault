"""
pb_summaries.py
===============
Protobuf parser to decode metadata and titles from agyhub_summaries_proto.pb.
"""
from __future__ import annotations
import os
import struct
import logging
from typing import Dict, List, Optional, Tuple
from ...models import ConversationMeta

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

def _decode_fields(data: bytes) -> List[Tuple[int, int, object]]:
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

def _decode_timestamp(raw: bytes) -> Optional[int]:
    for fn, wt, v in _decode_fields(raw):
        if fn == 1 and wt == 0:
            return v
    return None

def _as_str(v: object) -> Optional[str]:
    if isinstance(v, bytes):
        try:
            return v.decode('utf-8')
        except Exception:
            return None
    return str(v) if v is not None else None

def parse_summaries(pb_path: str) -> Dict[str, ConversationMeta]:
    if not os.path.isfile(pb_path):
        log.warning("agyhub_summaries_proto.pb not found at %s", pb_path)
        return {}

    try:
        with open(pb_path, 'rb') as fh:
            raw = fh.read()
    except Exception as e:
        log.error("Failed to read summaries pb at %s: %s", pb_path, e)
        return {}

    results: Dict[str, ConversationMeta] = {}

    for fn, wt, v in _decode_fields(raw):
        if fn != 1 or wt != 2:
            continue
        summary_fields = _decode_fields(v)
        conv_id: Optional[str] = None
        meta_raw: Optional[bytes] = None

        for sfn, swt, sv in summary_fields:
            if sfn == 1 and swt == 2:
                conv_id = _as_str(sv)
            elif sfn == 2 and swt == 2:
                meta_raw = sv

        if not conv_id or not meta_raw:
            continue

        title = conv_id
        step_count = 0
        created_at: Optional[int] = None
        updated_at: Optional[int] = None
        trajectory_id: Optional[str] = None

        for mfn, mwt, mv in _decode_fields(meta_raw):
            if mfn == 1 and mwt == 2:
                title = _as_str(mv) or title
            elif mfn == 2 and mwt == 0:
                step_count = mv
            elif mfn == 3 and mwt == 2:
                created_at = _decode_timestamp(mv)
            elif mfn == 4 and mwt == 2:
                trajectory_id = _as_str(mv)
            elif mfn == 7 and mwt == 2:
                updated_at = _decode_timestamp(mv)

        results[conv_id] = ConversationMeta(
            conversation_id=conv_id,
            title=title,
            step_count=step_count,
            created_at=created_at,
            updated_at=updated_at,
            trajectory_id=trajectory_id,
        )
        log.debug("Loaded metadata for %s: %s", conv_id[:8], title)

    log.info("Loaded %d conversation summaries from protobuf", len(results))
    return results
