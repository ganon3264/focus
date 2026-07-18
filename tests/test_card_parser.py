import base64
import json
import struct
import zlib

import pytest

from pyvern.card_parser import (
    _iter_chunks,
    _parse_text_chunk,
    _parse_itxt_chunk,
    extract_card_json,
    normalise_card,
    safe_load_card,
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

    return b"".join([
        signature,
        ihdr_len, b"IHDR", ihdr_data, ihdr_crc,
        length, ctype, chunk_data, crc,
        b"\x00\x00\x00\x00IEND", iend_crc,
    ])


def _chara_tEXt(card_dict: dict) -> bytes:
    """Build a tEXt chunk with base64-encoded character card data."""
    raw = base64.b64encode(json.dumps(card_dict).encode("latin-1")).decode("latin-1")
    payload = b"chara\x00" + raw.encode("latin-1")
    return payload


def _chara_iTXt(card_dict: dict, compressed: bool = False) -> bytes:
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
        result = _parse_itxt_chunk(b"key\x00\x00\x00\x00\x00" + "value".encode("utf-8"))
        assert result == ("key", "value")

    def test_compressed(self):
        compressed = zlib.compress(b"value")
        payload = b"key\x00\x01\x00\x00\x00" + compressed
        result = _parse_itxt_chunk(payload)
        assert result == ("key", "value")

    def test_no_null_returns_none(self):
        assert _parse_itxt_chunk(b"no null") is None


class TestExtractCardJson:
    def test_tEXt_chunk(self):
        card = {"name": "Test", "description": "A test card"}
        data = _png_with_chunk("tEXt", _chara_tEXt(card))
        result = extract_card_json(data)
        assert result == card

    def test_iTXt_chunk(self):
        card = {"name": "iTXt Card", "description": "From iTXt"}
        data = _png_with_chunk("iTXt", _chara_iTXt(card))
        result = extract_card_json(data)
        assert result == card

    def test_iTXt_compressed_chunk(self):
        card = {"name": "Compressed", "description": "zlib compressed"}
        data = _png_with_chunk("iTXt", _chara_iTXt(card, compressed=True))
        result = extract_card_json(data)
        assert result == card

    def test_no_chara_chunk_raises(self):
        data = _png_with_chunk("tEXt", b"other\x00data")
        with pytest.raises(ValueError, match="No 'chara' metadata"):
            extract_card_json(data)

    def test_non_base64_chunk_falls_back_to_raw_json(self):
        raw = json.dumps({"name": "Raw"}).encode("latin-1")
        payload = b"chara\x00" + raw
        data = _png_with_chunk("tEXt", payload)
        result = extract_card_json(data)
        assert result["name"] == "Raw"


class TestNormaliseCard:
    def test_v1_format(self):
        card = {"name": "V1", "description": "desc", "personality": "p",
                "scenario": "s", "mes_example": "m"}
        result = normalise_card(card)
        assert result["name"] == "V1"
        assert result["description"] == "desc"

    def test_v2_format_wrapped_in_data(self):
        card = {"data": {"name": "V2", "description": "desc"}}
        result = normalise_card(card)
        assert result["name"] == "V2"

    def test_missing_fields_use_defaults(self):
        result = normalise_card({})
        assert result["name"] == "Unknown"
        assert result["description"] == ""
        assert result["alternate_greetings"] == []

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
