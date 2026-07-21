import base64
import json
import struct
import zlib

import pytest

from focus.core.card_parser import (
    _iter_chunks,
    _parse_itxt_chunk,
    _parse_text_chunk,
    extract_card_json,
    normalise_card,
    parse_card_bytes,
    safe_load_card,
    validate_card_warnings,
)


def _png_with_chunk(chunk_type: str, chunk_data: bytes) -> bytes:
    """Build a minimal valid PNG containing a single metadata chunk."""
    signature = b"\x89PNG\r\n\x1a\n"

    # Minimal IHDR chunk (required): 1x1 pixel, 8-bit RGB
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr_len = struct.pack(">I", 13)
    ihdr_crc = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)

    # The metadata chunk
    length = struct.pack(">I", len(chunk_data))
    ctype = chunk_type.encode("ascii")
    crc = struct.pack(">I", zlib.crc32(ctype + chunk_data) & 0xFFFFFFFF)

    # Minimal IEND chunk
    iend_crc = struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)

    return b"".join(
        [
            signature,
            ihdr_len,
            b"IHDR",
            ihdr_data,
            ihdr_crc,
            length,
            ctype,
            chunk_data,
            crc,
            b"\x00\x00\x00\x00IEND",
            iend_crc,
        ]
    )


def _chara_text_v1(card_dict: dict) -> bytes:
    """Build a tEXt chunk with base64-encoded card under 'Chara' (capital C)."""
    raw = base64.b64encode(json.dumps(card_dict).encode("latin-1")).decode("latin-1")
    payload = b"Chara\x00" + raw.encode("latin-1")
    return payload


def _chara_text(card_dict: dict) -> bytes:
    """Build a tEXt chunk with base64-encoded character card data."""
    raw = base64.b64encode(json.dumps(card_dict).encode("latin-1")).decode("latin-1")
    payload = b"chara\x00" + raw.encode("latin-1")
    return payload


def _chara_itxt(card_dict: dict, compressed: bool = False) -> bytes:
    """Build an iTXt chunk with character card data."""
    text = json.dumps(card_dict).encode("utf-8")
    if compressed:
        text = zlib.compress(text)
    flag = b"\x01" if compressed else b"\x00"
    # keyword\x00 compression_flag compression_method language_tag\x00 translated_keyword\x00 text
    payload = b"chara\x00" + flag + b"\x00\x00\x00" + text
    return payload


class TestIterChunks:
    def test_invalid_signature_raises(self):
        with pytest.raises(ValueError, match="Not a valid PNG"):
            list(_iter_chunks(b"not a png"))

    def test_yields_chunks(self):
        data = _png_with_chunk("tEXt", b"key\x00value")
        chunks = list(_iter_chunks(data))
        types = [c[0] for c in chunks]
        assert "IHDR" in types
        assert "tEXt" in types
        assert "IEND" in types


class TestParseTextChunk:
    def test_parses_keyword_value(self):
        result = _parse_text_chunk(b"key\x00value")
        assert result == ("key", "value")

    def test_no_null_returns_none(self):
        assert _parse_text_chunk(b"no null here") is None


class TestParseITxtChunk:
    def test_uncompressed(self):
        result = _parse_itxt_chunk(b"key\x00\x00\x00\x00\x00" + b"value")
        assert result == ("key", "value")

    def test_compressed(self):
        compressed = zlib.compress(b"value")
        payload = b"key\x00\x01\x00\x00\x00" + compressed
        result = _parse_itxt_chunk(payload)
        assert result == ("key", "value")

    def test_no_null_returns_none(self):
        assert _parse_itxt_chunk(b"no null") is None


class TestExtractCardJson:
    def test_text_chunk(self):
        card = {"name": "Test", "description": "A test card"}
        data = _png_with_chunk("tEXt", _chara_text(card))
        result = extract_card_json(data)
        assert result == card

    def test_itxt_chunk(self):
        card = {"name": "iTXt Card", "description": "From iTXt"}
        data = _png_with_chunk("iTXt", _chara_itxt(card))
        result = extract_card_json(data)
        assert result == card

    def test_itxt_compressed_chunk(self):
        card = {"name": "Compressed", "description": "zlib compressed"}
        data = _png_with_chunk("iTXt", _chara_itxt(card, compressed=True))
        result = extract_card_json(data)
        assert result == card

    def test_no_chara_chunk_raises(self):
        data = _png_with_chunk("tEXt", b"other\x00data")
        with pytest.raises(ValueError, match="No 'ccv3' or 'chara' metadata"):
            extract_card_json(data)

    def test_non_base64_chunk_falls_back_to_raw_json(self):
        raw = json.dumps({"name": "Raw"}).encode("latin-1")
        payload = b"chara\x00" + raw
        data = _png_with_chunk("tEXt", payload)
        result = extract_card_json(data)
        assert result["name"] == "Raw"


class TestNormaliseCard:
    def test_v1_format(self):
        card = {
            "name": "V1",
            "description": "desc",
            "personality": "p",
            "scenario": "s",
            "mes_example": "m",
        }
        result = normalise_card(card)
        assert result["name"] == "V1"
        assert result["description"] == "desc"

    def test_v2_format_wrapped_in_data(self):
        card = {"data": {"name": "V2", "description": "desc"}}
        result = normalise_card(card)
        assert result["name"] == "V2"

    def test_missing_fields_use_defaults(self):
        result = normalise_card({})
        assert result["name"] == ""
        assert result["description"] == ""
        assert result["alternate_greetings"] == []
        assert result["extensions"] == {}
        assert result["tags"] == []

    def test_alternate_greetings_falsy_becomes_empty(self):
        result = normalise_card({"alternate_greetings": None})
        assert result["alternate_greetings"] == []


class TestSafeLoadCard:
    def test_valid_json_string(self):
        result = safe_load_card({"card_json": '{"name": "Test"}'})
        assert result["name"] == "Test"

    def test_none_row_returns_none(self):
        assert safe_load_card(None) is None

    def test_missing_card_json_returns_none(self):
        assert safe_load_card({}) is None

    def test_empty_card_json_returns_none(self):
        assert safe_load_card({"card_json": ""}) is None

    def test_invalid_json_returns_none(self):
        assert safe_load_card({"card_json": "not json"}) is None


class TestParseCardBytes:
    def test_png_bytes(self):
        card = {"name": "From PNG"}
        data = _png_with_chunk("tEXt", _chara_text(card))
        result = parse_card_bytes(data)
        assert result["name"] == "From PNG"

    def test_json_bytes(self):
        card = {"name": "From JSON"}
        data = json.dumps(card).encode("utf-8")
        result = parse_card_bytes(data)
        assert result["name"] == "From JSON"

    def test_neither_png_nor_json_raises(self):
        with pytest.raises(ValueError, match="Not a valid PNG or JSON"):
            parse_card_bytes(b"garbage data")


class TestExtractCardJsonCaseInsensitive:
    def test_capital_c_chara(self):
        card = {"name": "Capital C"}
        data = _png_with_chunk("tEXt", _chara_text_v1(card))
        result = extract_card_json(data)
        assert result["name"] == "Capital C"

    def test_lowercase_chara_still_works(self):
        card = {"name": "Lowercase"}
        data = _png_with_chunk("tEXt", _chara_text(card))
        result = extract_card_json(data)
        assert result["name"] == "Lowercase"


class TestValidateCardWarnings:
    def test_valid_v1_no_warnings(self):
        card = {"name": "Alice", "description": "A person"}
        assert validate_card_warnings(card) == []

    def test_valid_v2_no_warnings(self):
        card = {
            "spec": "chara_card_v2",
            "spec_version": "2.0",
            "data": {"name": "Bob", "description": "A robot"},
        }
        assert validate_card_warnings(card) == []

    def test_warns_unknown_spec(self):
        card = {"spec": "chara_card_v4", "data": {"name": "X"}}
        warnings = validate_card_warnings(card)
        assert any("Unknown spec" in w for w in warnings)

    def test_warns_wrong_spec_version(self):
        card = {"spec": "chara_card_v2", "spec_version": "1.0", "data": {"name": "X"}}
        warnings = validate_card_warnings(card)
        assert any("spec_version" in w for w in warnings)

    def test_warns_missing_name(self):
        card = {"description": "no name"}
        warnings = validate_card_warnings(card)
        assert any("Missing" in w and "name" in w for w in warnings)

    def test_warns_non_string_name(self):
        card = {"name": 42}
        warnings = validate_card_warnings(card)
        assert any("name" in w and "string" in w.lower() for w in warnings)

    def test_warns_non_string_field(self):
        card = {"name": "X", "description": 123}
        warnings = validate_card_warnings(card)
        assert any("description" in w for w in warnings)

    def test_warns_non_list_alternate_greetings(self):
        card = {"name": "X", "alternate_greetings": "not a list"}
        warnings = validate_card_warnings(card)
        assert any("alternate_greetings" in w for w in warnings)

    def test_warns_non_list_tags(self):
        card = {"name": "X", "tags": "not a list"}
        warnings = validate_card_warnings(card)
        assert any("tags" in w for w in warnings)

    def test_warns_non_dict_extensions(self):
        card = {"name": "X", "extensions": "not a dict"}
        warnings = validate_card_warnings(card)
        assert any("extensions" in w for w in warnings)


class TestNormaliseCardV2Preservation:
    def test_preserves_extensions(self):
        card = {
            "spec": "chara_card_v2",
            "spec_version": "2.0",
            "data": {
                "name": "Ex",
                "extensions": {"focus/custom": "value"},
            },
        }
        result = normalise_card(card)
        assert result["extensions"] == {"focus/custom": "value"}
        assert result["spec"] == "chara_card_v2"
        assert result["spec_version"] == "2.0"

    def test_extensions_defaults_to_empty_dict(self):
        card = {"data": {"name": "NoExt"}}
        result = normalise_card(card)
        assert result["extensions"] == {}

    def test_preserves_character_book(self):
        book = {"name": "Lore", "entries": []}
        card = {"spec": "chara_card_v2", "spec_version": "2.0", "data": {"name": "X", "character_book": book}}
        result = normalise_card(card)
        assert result["character_book"] == book

    def test_preserves_tags(self):
        card = {"data": {"name": "X", "tags": ["fantasy", "elf"]}}
        result = normalise_card(card)
        assert result["tags"] == ["fantasy", "elf"]

    def test_preserves_system_prompt(self):
        card = {"data": {"name": "X", "system_prompt": "You are a helpful assistant."}}
        result = normalise_card(card)
        assert result["system_prompt"] == "You are a helpful assistant."

    def test_preserves_creator_notes(self):
        card = {"data": {"name": "X", "creator_notes": "My notes"}}
        result = normalise_card(card)
        assert result["creator_notes"] == "My notes"

    def test_preserves_creator_and_version(self):
        card = {"data": {"name": "X", "creator": "Me", "character_version": "1.0"}}
        result = normalise_card(card)
        assert result["creator"] == "Me"
        assert result["character_version"] == "1.0"

    def test_name_empty_string_when_missing(self):
        result = normalise_card({})
        assert result["name"] == ""


# ── V3 ──────────────────────────────────────────────────────────────────────


class TestExtractCardJsonV3:
    def test_ccv3_chunk(self):
        card = {"spec": "chara_card_v3", "data": {"name": "V3 Char"}}
        payload = _chara_text(card).replace(b"chara", b"ccv3")
        data = _png_with_chunk("tEXt", payload)
        result = extract_card_json(data)
        assert result["spec"] == "chara_card_v3"
        assert result["data"]["name"] == "V3 Char"

    def test_ccv3_preferred_over_chara(self):
        """When both chunks exist, ccv3 wins."""
        chara_card = {"name": "Old"}
        ccv3_card = {"spec": "chara_card_v3", "data": {"name": "New"}}
        ccv3_payload = _chara_text(ccv3_card).replace(b"chara", b"ccv3")
        png = _png_with_chunk("tEXt", _chara_text(chara_card) + b"padding")
        # Append a second tEXt chunk for ccv3 by building from scratch
        signature = b"\x89PNG\r\n\x1a\n"
        ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        ihdr_chunk = struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)
        chara_len = struct.pack(">I", len(_chara_text(chara_card)))
        chara_crc = struct.pack(">I", zlib.crc32(b"tEXt" + _chara_text(chara_card)) & 0xFFFFFFFF)
        ccv3_len = struct.pack(">I", len(ccv3_payload))
        ccv3_crc = struct.pack(">I", zlib.crc32(b"tEXt" + ccv3_payload) & 0xFFFFFFFF)
        iend_crc = struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
        data = b"".join([signature, ihdr_chunk, chara_len, b"tEXt", _chara_text(chara_card), chara_crc, ccv3_len, b"tEXt", ccv3_payload, ccv3_crc, b"\x00\x00\x00\x00IEND", iend_crc])
        result = extract_card_json(data)
        assert result["spec"] == "chara_card_v3"
        assert result["data"]["name"] == "New"


class TestValidateCardWarningsV3:
    def test_valid_v3_no_warnings(self):
        card = {
            "spec": "chara_card_v3",
            "spec_version": "3.0",
            "data": {"name": "V3", "group_only_greetings": []},
        }
        assert validate_card_warnings(card) == []

    def test_v3_future_version_warns(self):
        card = {"spec": "chara_card_v3", "spec_version": "3.1", "data": {"name": "X"}}
        warnings = validate_card_warnings(card)
        assert any("newer" in w for w in warnings)

    def test_v3_warns_non_list_group_only_greetings(self):
        card = {"spec": "chara_card_v3", "data": {"name": "X", "group_only_greetings": "not a list"}}
        warnings = validate_card_warnings(card)
        assert any("group_only_greetings" in w for w in warnings)

    def test_v3_warns_non_list_assets(self):
        card = {"spec": "chara_card_v3", "data": {"name": "X", "assets": "not a list"}}
        warnings = validate_card_warnings(card)
        assert any("assets" in w for w in warnings)

    def test_v3_warns_non_list_source(self):
        card = {"spec": "chara_card_v3", "data": {"name": "X", "source": "not a list"}}
        warnings = validate_card_warnings(card)
        assert any("source" in w for w in warnings)

    def test_v3_warns_non_string_nickname(self):
        card = {"spec": "chara_card_v3", "data": {"name": "X", "nickname": 42}}
        warnings = validate_card_warnings(card)
        assert any("nickname" in w for w in warnings)

    def test_v3_warns_non_bool_use_regex(self):
        card = {
            "spec": "chara_card_v3",
            "data": {
                "name": "X",
                "character_book": {"entries": [{"use_regex": "not a bool"}]},
            },
        }
        warnings = validate_card_warnings(card)
        assert any("use_regex" in w for w in warnings)


class TestNormaliseCardV3Fields:
    def test_preserves_nickname(self):
        card = {"data": {"name": "Full", "nickname": "Nick"}}
        result = normalise_card(card)
        assert result["nickname"] == "Nick"

    def test_preserves_group_only_greetings(self):
        card = {"data": {"name": "X", "group_only_greetings": ["Hello group", "Hi group"]}}
        result = normalise_card(card)
        assert result["group_only_greetings"] == ["Hello group", "Hi group"]

    def test_group_only_greetings_defaults_to_empty(self):
        card = {"data": {"name": "X"}}
        result = normalise_card(card)
        assert result["group_only_greetings"] == []

    def test_preserves_assets(self):
        assets = [{"type": "icon", "uri": "embeded://icon.png", "name": "main", "ext": "png"}]
        card = {"data": {"name": "X", "assets": assets}}
        result = normalise_card(card)
        assert result["assets"] == assets

    def test_preserves_creator_notes_multilingual(self):
        ml = {"en": "Hello", "ja": "こんにちは"}
        card = {"data": {"name": "X", "creator_notes_multilingual": ml}}
        result = normalise_card(card)
        assert result["creator_notes_multilingual"] == ml

    def test_preserves_source(self):
        card = {"data": {"name": "X", "source": ["https://example.com"]}}
        result = normalise_card(card)
        assert result["source"] == ["https://example.com"]

    def test_preserves_dates(self):
        card = {"data": {"name": "X", "creation_date": 1234567890, "modification_date": 1234567899}}
        result = normalise_card(card)
        assert result["creation_date"] == 1234567890
        assert result["modification_date"] == 1234567899
