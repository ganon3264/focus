"""
PNG character card parser.

ST cards embed character JSON in PNG tEXt or iTXt chunks under the key "chara".
The value is base64-encoded JSON (spec v1 and v2 both use this).

We don't use Pillow here — raw struct parsing is faster and avoids
re-encoding the image. We just scan chunks ourselves.
"""

import base64
import json
import struct
import zlib


def _iter_chunks(data: bytes):
    """Yield (chunk_type, chunk_data) for every chunk in a PNG."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Not a valid PNG file")
    pos = 8
    while pos + 12 <= len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        ctype = data[pos + 4 : pos + 8].decode("ascii", errors="replace")
        cdata = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        yield ctype, cdata


def _parse_text_chunk(cdata: bytes) -> tuple[str, str] | None:
    """Parse a tEXt chunk → (keyword, value) or None."""
    null = cdata.find(b"\x00")
    if null < 0:
        return None
    return (
        cdata[:null].decode("latin-1"),
        cdata[null + 1 :].decode("latin-1"),
    )


def _parse_itxt_chunk(cdata: bytes) -> tuple[str, str] | None:
    """Parse an iTXt chunk → (keyword, text) or None."""
    null = cdata.find(b"\x00")
    if null < 0:
        return None
    keyword = cdata[:null].decode("utf-8", errors="ignore")
    rest = cdata[null + 1 :]
    if len(rest) < 2:
        return None
    compression_flag = rest[0]
    rest = rest[2:]  # skip compression_flag + compression_method
    # skip language tag
    n = rest.find(b"\x00")
    rest = rest[n + 1 :]
    # skip translated keyword
    n = rest.find(b"\x00")
    text_bytes = rest[n + 1 :]
    if compression_flag:
        text_bytes = zlib.decompress(text_bytes)
    return keyword, text_bytes.decode("utf-8", errors="ignore")


def extract_card_json(png_bytes: bytes) -> dict:
    """
    Extract and return the character card dict from a PNG.
    Raises ValueError if no card data is found.
    """
    for ctype, cdata in _iter_chunks(png_bytes):
        pair = None
        if ctype == "tEXt":
            pair = _parse_text_chunk(cdata)
        elif ctype == "iTXt":
            pair = _parse_itxt_chunk(cdata)

        if pair and pair[0] == "chara":
            raw = pair[1]
            try:
                return json.loads(base64.b64decode(raw.encode("latin-1")))
            except Exception:
                # Some cards store raw JSON without base64 (non-standard)
                try:
                    return json.loads(raw)
                except Exception:
                    pass

    raise ValueError("No 'chara' metadata found in PNG")


def normalise_card(card_json: dict) -> dict:
    """
    Return a flat dict of the standard fields, handling v1 and v2 formats.
    v2 wraps everything under a 'data' key.
    """
    src = card_json.get("data", card_json)
    return {
        "name":        src.get("name", "Unknown"),
        "description": src.get("description", ""),
        "personality": src.get("personality", ""),
        "scenario":    src.get("scenario", ""),
        "mes_example": src.get("mes_example", ""),
        "first_mes":   src.get("first_mes", ""),
    }
