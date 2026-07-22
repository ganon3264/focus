# External Tool Config Schema

Place a `.json` file in `tools/` at the project root. It is loaded automatically on startup.

```json
{
  "name": "my_tool",
  "description": "What the tool does",
  "command": ["python3", "tools/my_tool.py"],
  "params": [
    {
      "name": "param_name",
      "type": "string",
      "description": "Parameter description",
      "required": true
    }
  ],
  "writes": false,
  "multimodal": false,
  "timeout": 30
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `string` | — | Unique tool name shown to the LLM |
| `description` | `string` | — | LLM-facing description of what the tool does |
| `command` | `string` or `array` | — | Executable and args. A string is split with `shlex.split`. |
| `params` | `array` | `[]` | List of accepted parameters (see below) |
| `writes` | `bool` | `false` | When `true`, hidden in read-only mode |
| `multimodal` | `bool` | `false` | When `true`, tool may return image data (see Script Contract) |
| `timeout` | `int` | `30` | Subprocess timeout in seconds |

### Param object

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `string` | — | Parameter name sent to the LLM |
| `type` | `string` | — | One of: `string`, `integer`, `boolean`, `number` |
| `description` | `string` | `""` | LLM-facing description |
| `required` | `bool` | `true` | If `false`, the LLM may omit it |

# Script Contract

The tool script receives parameters as JSON on **stdin** and must return output on **stdout**.

### Input (stdin)

```json
{"param_name": "value", "other_param": 42}
```

### Output (stdout)

**Success** — return a JSON object with an `"output"` key, or any other JSON / plain text:

```json
{"output": "result string"}
```

**Error** — return a JSON object with an `"error"` key, or exit non-zero (stderr is included in the error message):

```json
{"error": "something went wrong"}
```

**Image return** — return a JSON object with an `"image"` key. Requires `"multimodal": true`
in the tool config. The `"image"` value is an object with these fields:

| Field | Type | Required | Description |
|---|---|---|---|
| `base64` | `string` | yes | Base64-encoded image bytes |
| `mime` | `string` | no | MIME type, defaults to `image/png` |
| `path` | `string` | no | Source path (informational) |
| `description` | `string` | no | Text shown alongside the image |

```json
{"image": {"base64": "iVBORw0KGgo...", "mime": "image/png", "description": "Screenshot of desktop"}}
```

A tool may also include an `"output"` key alongside `"image"` — the text output is
fed back to the model as a tool result, and the image is injected as a subsequent
user message with multimodal content.

Output is truncated at 32,000 characters. Invalid JSON configs are skipped (logged as a warning).

# Example

`tools/count_words.json`:

```json
{
  "name": "count_words",
  "description": "Count the number of words in a given text.",
  "command": ["python3", "tools/count_words.py"],
  "params": [
    {
      "name": "text",
      "type": "string",
      "description": "The text to count words in",
      "required": true
    }
  ],
  "writes": false
}
```

`tools/count_words.py`:

```python
#!/usr/bin/env python3
import json, sys

data = json.load(sys.stdin)
text = data.get("text", "")
count = len(text.split())
print(json.dumps({"output": str(count)}))
```

Place both files in `tools/`, click reload in the tools modal, and the tool is available to the LLM.

# Image Example

`tools/screenshot.json`:

```json
{
  "name": "screenshot",
  "description": "Take a screenshot of the desktop and return it as an image.",
  "command": ["python3", "tools/screenshot.py"],
  "multimodal": true,
  "params": [],
  "writes": false
}
```

`tools/screenshot.py`:

```python
#!/usr/bin/env python3
import subprocess, json, base64, sys

result = subprocess.run(["import", "-window", "root", "png:-"],
                        capture_output=True, timeout=10)
b64 = base64.b64encode(result.stdout).decode()
print(json.dumps({
    "image": {
        "base64": b64,
        "mime": "image/png",
        "description": "Current desktop screenshot",
    },
}))
```

Place both files in `tools/`, click reload in the tools modal, and the tool is available
to vision-capable models (the sampler must have multimodal tools enabled).
