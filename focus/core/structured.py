"""Structured responses: JSON-schema-constrained completions rendered through a
Handlebars template.

The schema is sent upstream as OpenAI-style ``response_format``; the model's
JSON reply is parsed (with repair for truncated output) and passed through a
Handlebars template to produce the stored message text. Port of the
StructuredResponses SillyTavern extension, run server-side.
"""

from __future__ import annotations

import json
import re

import json_repair
from pybars import Compiler

from .macros import apply_macros

_compiler = Compiler()

_NAME_SANITIZE = re.compile(r"[^a-zA-Z0-9_-]")


def resolve_schema(schema_text: str, macros: dict[str, str]):
    """Parse the schema JSON, then resolve macros in string values and keys.

    Macros are applied only after parsing, so their output can never change the
    JSON structure (mirrors the extension's ``parseJsonSchema``).
    """
    try:
        schema = json.loads(schema_text)
    except (TypeError, ValueError) as e:
        raise ValueError(f"schema is not valid JSON: {e}") from e

    def substitute(value):
        if isinstance(value, str):
            return apply_macros(value, macros)
        if isinstance(value, list):
            return [substitute(v) for v in value]
        if isinstance(value, dict):
            out: dict = {}
            for key, item in value.items():
                resolved_key = apply_macros(key, macros) if isinstance(key, str) else key
                if resolved_key in out:
                    raise ValueError(
                        f"duplicate schema key after macro substitution: {resolved_key}"
                    )
                out[resolved_key] = substitute(item)
            return out
        return value

    return substitute(schema)


def _unwrap_set_wrapper(schema):
    """Accept the SillyTavern set wrapper ``{name, strict, value}`` as well as a
    bare JSON Schema, so schemas copied from preset files work verbatim."""
    if (
        isinstance(schema, dict)
        and isinstance(schema.get("value"), (dict, list))
        and any(k in schema for k in ("name", "strict", "description", "returnInvalid"))
    ):
        return schema["value"], schema
    return schema, None


def build_response_format(row: dict, macros: dict[str, str]) -> dict:
    """OpenAI-style ``response_format`` payload for a structured response row."""
    schema = resolve_schema(row.get("json_schema") or "", macros)
    schema, wrapper = _unwrap_set_wrapper(schema)

    name = (row.get("name") or "Response").strip()
    description = None
    strict = True
    if wrapper:
        name = (wrapper.get("name") or name).strip()
        description = wrapper.get("description")
        strict = bool(wrapper.get("strict", True))
    name = _NAME_SANITIZE.sub("_", name) or "Response"

    json_schema: dict = {"name": name, "strict": strict, "schema": schema}
    if description:
        json_schema["description"] = description
    return {"type": "json_schema", "json_schema": json_schema}


def parse_structured(raw) -> dict | list | None:
    """Parse a model reply as JSON, repairing truncated/invalid output."""
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        pass
    try:
        repaired = json_repair.loads(text)
    except Exception:
        return None
    return repaired if isinstance(repaired, (dict, list)) else None


def validate_schema_text(schema_text: str) -> str | None:
    """Return an error string when the schema is not valid JSON. Macros are not
    executed (editing must not have side effects)."""
    if not schema_text.strip():
        return "Schema is empty."
    try:
        json.loads(schema_text)
    except (TypeError, ValueError) as e:
        return f"Invalid JSON: {e}"
    return None


def validate_template(template: str) -> str | None:
    if not template.strip():
        return "Template is empty."
    try:
        _compiler.compile(template)
    except Exception as e:
        return f"Invalid template: {e}"
    return None


def render_structured(raw, template: str, macros: dict[str, str]) -> str:
    """Parse the reply and render it through the Handlebars template."""
    data = parse_structured(raw)
    if data is None:
        raise ValueError("model response is not valid JSON")
    compiled = _compiler.compile(template)
    return str(compiled(data, helpers=_build_helpers(macros)))


# ── Handlebars helpers (port of the extension's helpers.js) ──────────────────


def _wrap(fn):
    """Normalise pybars' calling convention.

    Block helpers are called as ``fn(this, options, *args)``; inline helpers and
    subexpressions as ``fn(this, *args)``. ``args[0]`` is an options dict only
    for block helpers, so detect it by the ``helpers`` marker.
    """

    def helper(this, *args, **kwargs):
        options = None
        if args and isinstance(args[0], dict) and "helpers" in args[0]:
            options = args[0]
            args = args[1:]
        if options is not None:
            return fn(*args, options=options, **kwargs)
        return fn(*args, **kwargs)

    return helper


def _replace(s, search, replacement="", **kwargs):
    if not isinstance(s, str) or not isinstance(search, str):
        return s
    match = re.match(r"^/([\s\S]+)/([gimyus]*)$", search)
    if match:
        flags = 0
        js_flags = match.group(2)
        if "i" in js_flags:
            flags |= re.IGNORECASE
        if "m" in js_flags:
            flags |= re.MULTILINE
        if "s" in js_flags:
            flags |= re.DOTALL
        count = 0 if "g" in js_flags else 1
        try:
            return re.sub(match.group(1), replacement, s, count=count, flags=flags)
        except re.error:
            return s
    return s.replace(search, replacement)


def _split(s, separator="", **kwargs):
    if not isinstance(s, str):
        return []
    if separator == "":
        return list(s)
    return s.split(separator)


def _substring(s, start, end=None, **kwargs):
    if not isinstance(s, str):
        return s
    length = len(s)
    a = max(0, min(length, int(start)))
    b = length if end is None else max(0, min(length, int(end)))
    if a > b:
        a, b = b, a
    return s[a:b]


def _slice(arr, start=0, end=None, **kwargs):
    if not isinstance(arr, (list, tuple)):
        return []
    return list(arr[start:end])


def _build_helpers(macros: dict[str, str]) -> dict:
    return {
        "eq": _wrap(lambda a, b, **k: a == b),
        "ne": _wrap(lambda a, b, **k: a != b),
        "lt": _wrap(lambda a, b, **k: a < b),
        "gt": _wrap(lambda a, b, **k: a > b),
        "lte": _wrap(lambda a, b, **k: a <= b),
        "gte": _wrap(lambda a, b, **k: a >= b),
        "and": _wrap(lambda *args, **k: all(args)),
        "or": _wrap(lambda *args, **k: any(args)),
        "not": _wrap(lambda val, **k: not val),
        "default": _wrap(lambda val, fallback, **k: val or fallback),
        "add": _wrap(lambda a, b, **k: _number(a) + _number(b)),
        "sub": _wrap(lambda a, b, **k: _number(a) - _number(b)),
        "mul": _wrap(lambda a, b, **k: _number(a) * _number(b)),
        "div": _wrap(lambda a, b, **k: _number(a) / _number(b)),
        "json": _wrap(lambda value, **k: json.dumps(value, ensure_ascii=False, default=str)),
        "upper": _wrap(lambda s, **k: s.upper() if isinstance(s, str) else s),
        "lower": _wrap(lambda s, **k: s.lower() if isinstance(s, str) else s),
        "trim": _wrap(lambda s, **k: s.strip() if isinstance(s, str) else s),
        "replace": _wrap(_replace),
        "split": _wrap(_split),
        "substring": _wrap(_substring),
        "includes": _wrap(
            lambda val, search, **k: search in val if isinstance(val, (list, str)) else False
        ),
        "length": _wrap(
            lambda val, **k: len(val) if isinstance(val, (list, str)) else 0
        ),
        "join": _wrap(lambda arr, sep="", **k: sep.join(str(x) for x in arr) if isinstance(arr, list) else arr),
        "first": _wrap(lambda arr, **k: arr[0] if isinstance(arr, list) and arr else arr),
        "last": _wrap(lambda arr, **k: arr[-1] if isinstance(arr, list) and arr else arr),
        "slice": _wrap(_slice),
        "macro": _wrap(
            lambda s, **k: apply_macros(s, macros) if isinstance(s, str) else s
        ),
    }


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
