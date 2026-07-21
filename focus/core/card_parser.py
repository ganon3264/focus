"""
PNG / JSON character card parser.

ST cards embed character JSON in PNG tEXt or iTXt chunks under the key "chara"
(or "Chara" per V1 spec).  The value is base64-encoded JSON (spec v1 and v2
both use this).  Plain .json files are also accepted.

We don't use Pillow here — raw struct parsing is faster and avoids
re-encoding the image. We just scan chunks ourselves.
"""

import base64
import json
import logging
import struct
import zlib

logger = logging.getLogger("focus.card_parser")

_CHARA_KEYWORDS = {"chara", "Chara"}
_CCV3_KEYWORD = "ccv3"

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
    n = rest.find(b"\x00")
    rest = rest[n + 1 :]
    n = rest.find(b"\x00")
    text_bytes = rest[n + 1 :]
    if compression_flag:
        try:
            text_bytes = zlib.decompress(text_bytes)
        except zlib.error as e:
            logger.debug("zlib decompress failed for iTXt chunk: %s", e)
            return None
    return keyword, text_bytes.decode("utf-8", errors="ignore")


def _decode_chunk_data(raw: str) -> dict | None:
    """Try base64 decode then raw JSON parse on chunk value."""
    try:
        return json.loads(base64.b64decode(raw.encode("latin-1")))
    except Exception:
        logger.debug("chunk not valid base64, trying raw JSON", exc_info=True)
        try:
            return json.loads(raw)
        except Exception:
            logger.debug("raw JSON parse also failed, skipping chunk", exc_info=True)
    return None


def extract_card_json(png_bytes: bytes) -> dict:
    """
    Extract and return the character card dict from a PNG.
    Prefers the ``ccv3`` chunk (V3 spec), then falls back to ``chara``/``Chara`` (V1/V2).
    Raises ValueError if no card data is found.
    """
    chara_fallback: dict | None = None

    for ctype, cdata in _iter_chunks(png_bytes):
        pair = None
        if ctype == "tEXt":
            pair = _parse_text_chunk(cdata)
        elif ctype == "iTXt":
            pair = _parse_itxt_chunk(cdata)

        if not pair:
            continue

        # ccv3 chunk — return immediately (preferred)
        if pair[0] == _CCV3_KEYWORD:
            result = _decode_chunk_data(pair[1])
            if result is not None:
                return result
            continue

        # chara/Chara — save as fallback; don't return yet in case ccv3 follows
        if pair[0] in _CHARA_KEYWORDS:
            if chara_fallback is None:
                chara_fallback = _decode_chunk_data(pair[1])

    if chara_fallback is not None:
        return chara_fallback

    raise ValueError("No 'ccv3' or 'chara' metadata found in PNG")


def parse_card_bytes(data: bytes) -> dict:
    """Parse character card from raw bytes (PNG or JSON).

    Tries PNG extraction first, then falls back to JSON parsing.
    Raises ValueError if neither works.
    """
    try:
        return extract_card_json(data)
    except ValueError:
        pass
    try:
        return json.loads(data)
    except json.JSONDecodeError as e:
        raise ValueError(f"Not a valid PNG or JSON file: {e}")


_KNOWN_SPECS = {"chara_card_v2", "chara_card_v3"}


def validate_card_warnings(card_json: dict) -> list[str]:
    """Check card against the V1/V2/V3 spec and return a list of warnings.

    Lenient — never raises, only returns strings describing spec violations.
    """
    warnings: list[str] = []
    src = card_json.get("data", card_json)

    spec = card_json.get("spec")
    if spec is not None and spec not in _KNOWN_SPECS:
        warnings.append(f"Unknown spec: '{spec}'")

    spec_version = card_json.get("spec_version")
    if spec == "chara_card_v2" and spec_version != "2.0":
        warnings.append(f"Expected spec_version '2.0', got '{spec_version}'")
    if spec == "chara_card_v3":
        if spec_version != "3.0":
            try:
                if float(spec_version) > 3.0:
                    warnings.append(
                        f"Card uses newer spec version '{spec_version}' — some features may not be supported"
                    )
                else:
                    warnings.append(f"Expected spec_version '3.0', got '{spec_version}'")
            except (ValueError, TypeError):
                warnings.append(f"Expected spec_version '3.0', got '{spec_version}'")

    name = src.get("name")
    if not name:
        warnings.append("Missing or empty character name")
    elif not isinstance(name, str):
        warnings.append(f"Character name should be a string, got {type(name).__name__}")

    for field in ("description", "personality", "scenario", "first_mes", "mes_example"):
        val = src.get(field)
        if val is not None and not isinstance(val, str):
            warnings.append(f"Field '{field}' should be a string, got {type(val).__name__}")

    alt = src.get("alternate_greetings")
    if alt is not None and not isinstance(alt, list):
        warnings.append(f"Field 'alternate_greetings' should be an array, got {type(alt).__name__}")

    tags = src.get("tags")
    if tags is not None and not isinstance(tags, list):
        warnings.append(f"Field 'tags' should be an array, got {type(tags).__name__}")

    ext = src.get("extensions")
    if ext is not None and not isinstance(ext, dict):
        warnings.append(f"Field 'extensions' should be an object, got {type(ext).__name__}")

    # V3 field type checks
    group_greetings = src.get("group_only_greetings")
    if group_greetings is not None and not isinstance(group_greetings, list):
        warnings.append(f"Field 'group_only_greetings' should be an array, got {type(group_greetings).__name__}")

    assets = src.get("assets")
    if assets is not None and not isinstance(assets, list):
        warnings.append(f"Field 'assets' should be an array, got {type(assets).__name__}")

    source = src.get("source")
    if source is not None and not isinstance(source, list):
        warnings.append(f"Field 'source' should be an array, got {type(source).__name__}")

    nickname = src.get("nickname")
    if nickname is not None and not isinstance(nickname, str):
        warnings.append(f"Field 'nickname' should be a string, got {type(nickname).__name__}")

    # V3 character_book: check use_regex is boolean when present on entries
    character_book = src.get("character_book")
    if isinstance(character_book, dict):
        entries = character_book.get("entries", [])
        if isinstance(entries, list):
            for i, entry in enumerate(entries):
                if isinstance(entry, dict) and "use_regex" in entry and not isinstance(entry["use_regex"], bool):
                    warnings.append(f"character_book.entries[{i}].use_regex should be a boolean, got {type(entry['use_regex']).__name__}")

    return warnings


def normalise_card(card_json: dict) -> dict:
    """
    Return a flat dict of card fields, handling v1 and v2 formats.

    V2 wraps core fields under a ``data`` key.  All recognised V2 fields are
    preserved as pass-through.  Unknown key-value pairs inside ``extensions``
    are never destroyed.
    """
    src = card_json.get("data", card_json)

    return {
        # Core V1 fields with safe defaults (empty string per spec)
        "name": src.get("name") or "",
        "description": src.get("description", ""),
        "personality": src.get("personality", ""),
        "scenario": src.get("scenario", ""),
        "mes_example": src.get("mes_example", ""),
        "first_mes": src.get("first_mes", ""),
        "alternate_greetings": src.get("alternate_greetings") or [],
        # V2 spec identifiers
        "spec": card_json.get("spec"),
        "spec_version": card_json.get("spec_version"),
        # V2 fields (preserved even if Focus doesn't use them internally)
        "creator_notes": src.get("creator_notes", ""),
        "system_prompt": src.get("system_prompt", ""),
        "post_history_instructions": src.get("post_history_instructions", ""),
        "tags": src.get("tags") or [],
        "creator": src.get("creator", ""),
        "character_version": src.get("character_version", ""),
        "character_book": src.get("character_book"),
        "extensions": src.get("extensions") or {},
        # V3 fields
        "nickname": src.get("nickname"),
        "group_only_greetings": src.get("group_only_greetings") or [],
        "assets": src.get("assets"),
        "creator_notes_multilingual": src.get("creator_notes_multilingual"),
        "source": src.get("source"),
        "creation_date": src.get("creation_date"),
        "modification_date": src.get("modification_date"),
    }


def safe_load_card(row, *, log_name: str | None = None) -> dict | None:
    """Parse and normalise the `card_json` field from a DB row or dict.

    Returns the normalised card dict on success.
    Returns None if card_json is missing/empty or unparseable; callers should
    decide what fallback they want (empty dict, specific shape, early-return).
    A warning is logged on parse failure with a row identifier when available.
    """
    try:
        raw = row["card_json"]
    except (KeyError, TypeError):
        return None
    if not raw:
        return None
    try:
        return normalise_card(json.loads(raw))
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        if log_name is None:
            try:
                log_name = f"{row['id']} ({row['name']})"
            except (KeyError, IndexError, TypeError):
                log_name = "?"
        logger.warning("Corrupted card_json for %s: %s", log_name, e)
        return None
