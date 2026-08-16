"""Unit tests for external tool loading/execution (focus/tools/external.py)."""

import json
import sys

import pytest

from focus.tools import ToolParam, ToolSpec
from focus.tools.external import (
    ExternalToolConfig,
    ToolParamDef,
    _coerce_array_params,
    _load_single_tool,
    _parse_command,
    _run_external_tool,
    load_external_tools,
)
from focus.tools.provider_adapter import to_provider_tools


def _script(source: str) -> list[str]:
    return [sys.executable, "-c", source]


class TestParseCommand:
    def test_string_shlex_split(self):
        assert _parse_command("python -m tool --flag") == ["python", "-m", "tool", "--flag"]
        assert _parse_command('echo "quoted arg"') == ["echo", "quoted arg"]

    def test_list_passthrough(self):
        assert _parse_command(["a", "b"]) == ["a", "b"]


class TestRunExternalTool:
    def test_echo_stdin_json(self):
        out = _run_external_tool(["cat"], {"a": 1})
        assert json.loads(out) == {"a": 1}

    def test_output_key_unwrapped(self):
        script = (
            "import json, sys; "
            "data = json.load(sys.stdin); "
            "print(json.dumps({'output': 'got ' + str(data['a'])}))"
        )
        assert _run_external_tool(_script(script), {"a": 42}) == "got 42"

    def test_image_dict_passthrough(self):
        script = (
            "import json, sys; "
            "json.load(sys.stdin); "
            "print(json.dumps({'image': {'base64': 'AAAA', 'mime': 'image/png'}}))"
        )
        out = _run_external_tool(_script(script), {})
        assert out["image"]["base64"] == "AAAA"

    def test_error_key_raises(self):
        script = "import json, sys; json.load(sys.stdin); print(json.dumps({'error': 'boom'}))"
        with pytest.raises(RuntimeError, match="boom"):
            _run_external_tool(_script(script), {})

    def test_non_zero_exit_raises(self):
        with pytest.raises(RuntimeError, match="nope"):
            _run_external_tool(_script("import sys; print('nope', file=sys.stderr); sys.exit(3)"), {})

    def test_non_json_stdout_returned_raw(self):
        out = _run_external_tool(_script("import sys; sys.stdin.read(); print('raw text')"), {})
        assert out == "raw text\n"


class TestLoadSingleTool:
    def test_valid_config(self, tmp_path):
        cfg = {
            "name": "ext_tool",
            "description": "Does things",
            "command": f"{sys.executable} -c pass",
            "timeout": 5,
            "writes": True,
            "multimodal": True,
            "category": "Custom",
            "params": [
                {"name": "query", "type": "string", "description": "q", "required": True},
                {"name": "count", "type": "integer", "description": "c", "required": False},
            ],
        }
        path = tmp_path / "tool.json"
        path.write_text(json.dumps(cfg))
        spec = _load_single_tool(path)
        assert spec.name == "ext_tool"
        assert spec.writes is True
        assert spec.multimodal is True
        assert spec.category == "Custom"
        assert [p.name for p in spec.params] == ["query", "count"]
        assert spec.params[1].required is False

    def test_invalid_param_type_rejected(self, tmp_path):
        cfg = {
            "name": "bad",
            "description": "x",
            "command": "true",
            "params": [{"name": "p", "type": "nonsense"}],
        }
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(cfg))
        with pytest.raises(ValueError, match="type must be one of"):
            _load_single_tool(path)

    def test_array_param_with_items(self, tmp_path):
        cfg = {
            "name": "arr",
            "description": "x",
            "command": "true",
            "params": [{
                "name": "loras",
                "type": "array",
                "description": "list of loras",
                "required": False,
                "items": {"type": "object", "properties": {"name": {"type": "string"}}},
            }],
        }
        path = tmp_path / "arr.json"
        path.write_text(json.dumps(cfg))
        spec = _load_single_tool(path)
        p = spec.params[0]
        assert p.type == "array"
        assert p.required is False
        assert p.items == {"type": "object", "properties": {"name": {"type": "string"}}}

    def test_model_validation_errors(self):
        with pytest.raises(ValueError):
            ToolParamDef(name="p", type="bad")
        with pytest.raises(ValueError):
            ExternalToolConfig.model_validate({"name": "x", "description": "d", "command": 123})

    def test_command_list_config(self, tmp_path):
        cfg = {
            "name": "listy",
            "description": "x",
            "command": ["echo", "hi"],
        }
        path = tmp_path / "listy.json"
        path.write_text(json.dumps(cfg))
        assert _load_single_tool(path).name == "listy"


class TestCoerceArrayParams:
    def _defs(self):
        return [ToolParamDef(name="loras", type="array", items={"type": "object"})]

    def test_list_passthrough(self):
        out = _coerce_array_params({"loras": [{"name": "a"}]}, self._defs())
        assert out["loras"] == [{"name": "a"}]

    def test_json_string_parsed(self):
        out = _coerce_array_params({"loras": '[{"name": "a"}]'}, self._defs())
        assert out["loras"] == [{"name": "a"}]

    def test_plain_string_wrapped(self):
        out = _coerce_array_params({"loras": "my_lora"}, self._defs())
        assert out["loras"] == ["my_lora"]

    def test_scalar_wrapped(self):
        out = _coerce_array_params({"loras": 5}, self._defs())
        assert out["loras"] == [5]

    def test_none_left_alone(self):
        out = _coerce_array_params({"loras": None}, self._defs())
        assert out["loras"] is None

    def test_non_array_params_untouched(self):
        defs = [ToolParamDef(name="count", type="integer")]
        out = _coerce_array_params({"count": "5"}, defs)
        assert out["count"] == "5"


def test_to_provider_tools_includes_items():
    spec = ToolSpec(
        name="t",
        description="d",
        params=[
            ToolParam(
                name="loras",
                type="array",
                description="l",
                required=False,
                items={"type": "string"},
            )
        ],
        writes=False,
        handler=lambda **kw: None,
    )
    payload = to_provider_tools([spec])
    prop = payload[0]["function"]["parameters"]["properties"]["loras"]
    assert prop["type"] == "array"
    assert prop["items"] == {"type": "string"}


class TestLoadExternalTools:
    def _valid_config(self, name: str) -> dict:
        return {
            "name": name,
            "description": "d",
            "command": "true",
            "params": [],
        }

    def test_empty_when_dir_missing(self, tmp_path):
        assert load_external_tools(tmp_path / "missing") == []

    def test_scans_recursively_skips_broken_and_hidden(self, tmp_path):
        (tmp_path / "a.json").write_text(json.dumps(self._valid_config("top")))
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "b.json").write_text(json.dumps(self._valid_config("nested")))
        (tmp_path / "sub" / "broken.json").write_text("{not json")
        (tmp_path / ".hidden").mkdir()
        (tmp_path / ".hidden" / "c.json").write_text(json.dumps(self._valid_config("hidden")))
        (tmp_path / "deep" / "x" / "y").mkdir(parents=True)
        (tmp_path / "deep" / "x" / "y" / "d.json").write_text(json.dumps(self._valid_config("too_deep")))

        tools = load_external_tools(tmp_path)
        names = {t.name for t in tools}
        assert names == {"top", "nested"}
        assert "hidden" not in names
        assert "too_deep" not in names

    def test_loads_then_runs_handler(self, tmp_path):
        script = (
            "import json, sys; "
            "data = json.load(sys.stdin); "
            "print(json.dumps({'output': 'hello ' + data['who']}))"
        )
        cfg = self._valid_config("greeter")
        cfg["command"] = [sys.executable, "-c", script]
        cfg["params"] = [{"name": "who", "type": "string", "description": "w"}]
        (tmp_path / "greeter.json").write_text(json.dumps(cfg))

        tool = load_external_tools(tmp_path)[0]
        assert tool.handler(who="world") == "hello world"
