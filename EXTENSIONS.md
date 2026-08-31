# Extension Config Schema

An extension is a user-installed script that acts on a message in your chat. Unlike
**tools** (which the model invokes mid-generation), an extension is triggered by *you*
from the message toolbar. It runs in a trusted subprocess with **no sandbox** — the same
trust model as tools. **Verify the code before you install it.** It can read anything your
process can read, including `data/focus.db`, and run with your privileges.

Place a `.json` spec (plus, usually, a companion script) in `extensions/` at the project
root. It is loaded automatically on startup and re-scanned when you click **Reload**.

```json
{
  "name": "tts",
  "description": "Read the assistant's reply aloud",
  "command": ["python3", "extensions/tts.py"],
  "timeout": 120,
  "category": "Voice",
  "icon": "<svg viewBox='0 0 24 24' fill='none' stroke='currentColor' stroke-width='2'><path d='M11 5 6 9H2v6h4l5 4z'/></svg>",
  "roles": ["assistant"],
  "needs": ["message"],
  "triggers": ["manual"],
  "secrets": ["TTS_API_KEY"],
  "params": [
    {
      "name": "voice",
      "type": "string",
      "description": "Voice to speak with",
      "default": "en-US"
    }
  ]
}
```

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `string` | — | Unique extension name shown in the modal / toolbar |
| `description` | `string` | — | Shown in the modal |
| `command` | `string` or `array` | — | Executable + args. A string is split with `shlex.split`. |
| `timeout` | `int` | `30` | Subprocess timeout in seconds |
| `category` | `string` | `"General"` | Grouping shown in the extensions modal |
| `icon` | `string` | `""` | Raw SVG markup for the button/modal icon. **Trusted markup** — same trust level as the script, rendered via `innerHTML`. |
| `roles` | `array` | `["assistant"]` | Which message roles the extension applies to (`assistant`, `user`). Gating for both the toolbar button and auto-triggers. |
| `needs` | `array` | `["message"]` | Context included on stdin: `message`, `transcript` |
| `triggers` | `array` | `["manual"]` | Events that run this extension: `manual` (toolbar button) plus any of `generation_start`, `generation_end`, `edit`, `swipe`. Extensions without `manual` never show a toolbar button. |
| `secrets` | `array` | `[]` | Names of keys from the `secrets` table to inject (hygiene, *not* a security boundary — the script can read the DB anyway) |
| `params` | `array` | `[]` | User-config fields (auto-rendered form in the modal) |

### `params` object

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | `string` | — | Config key |
| `type` | `string` | — | One of: `string`, `integer`, `boolean`, `number`, `array` |
| `description` | `string` | `""` | Label in the form |
| `default` | any | `null` | Default value |
| `enum` | `array` | `null` | Restricted choices (rendered as a dropdown) |
| `items` | `object` | `null` | JSON Schema for array elements |

# Request (stdin)

Focus passes **one JSON object on stdin**:

```json
{
  "extension": {"name": "tts"},
  "chat": {
    "id": "...",
    "character": "Ada",
    "persona": "System Prompt",
    "preset": "Default",
    "provider": "openai_compat"
  },
  "target": {
    "message_id": "...",
    "variant_id": "...",
    "role": "assistant",
    "position": 3,
    "content": "The full raw text of the active variant.",
    "raw_content": "Same as content, un-resolved.",
    "segments": [
      {"type": "text", "content": "Only the spoken text..."},
      {"type": "tool_boundary", "tool_calls": []}
    ],
    "reasoning": null,
    "attachments": [{"file_path": "...", "mime_type": "image/png"}],
    "tool_calls": [],
    "model_name": "llama"
  },
  "transcript": [],
  "config": {"voice": "en-US"},
  "secrets": {"TTS_API_KEY": "…"}
}
```

- `target.content` is macro-resolved; `target.raw_content` is the stored text.
- `segments` are typed (`text | reasoning | tool_boundary`) so you can pick out just the
  spoken text with a one-liner instead of regex.
- `transcript` is only present when `needs` includes `"transcript"`. It is a list of
  `{role, content, segments}`.
- `secrets` contains **only** the keys listed in `secrets` (hygiene).
- There is no `writes` flag. Extensions are declarative — the side effect is whatever
  `action`/`files` they request, and Focus performs it. Don't fake a read-only/write
  boundary for a trusted script.

# Result (stdout)

Return **one JSON object on stdout**. Non-JSON stdout is treated as plain text content.

```json
{
  "status": "done",
  "error": "optional failure message",
  "content": "optional text to show",
  "action": {
    "type": "create_swipe",
    "message_id": "optional (defaults to target)",
    "content": "the rewritten text",
    "reasoning": null,
    "segments": null
  },
  "files": [
    {"name": "reply.mp3", "data": "<base64>", "mime": "audio/mpeg"}
  ],
  "logs": [
    {"level": "info", "message": "synthesizing 420 characters…"}
  ]
}
```

### Actions

| `action.type` | Effect |
|---|---|
| `create_swipe` | Write a **new variant** (a swipe) of `message_id`. The rewrite case. |
| *(none)* | If `files` are present they are attached to the target message. The TTS case. |

#### Rewriting preserves structure

A rewrite variant is a **clone of the source message**, not a fresh rebuild. The
source's reasoning and tool calls (and their position in the message) are always
carried over — they are never dropped or flattened.

- With **`action.content` only** (the simple case) the rewritten text replaces the
  source's spoken text. Single-text messages are exact. If the source interleaves
  text around a tool call or reasoning block, the structure is kept but the text is
  consolidated into the first text slot (the source's ordering of tool calls and
  reasoning is preserved).
- With **`action.segments`** you take full control: copy `target.segments`, rewrite
  each `text` segment in place, and return them. This is the exact path for messages
  that interleave text with tool calls / reasoning (e.g. `[text][tool][text]`), and
  is what makes a rewrite behave like a hand-edit. Non-`text` segments (reasoning,
  tool_boundary) stay just as they were.

### `files`

Written to the assets dir and bound to the target message as attachments. Each entry has
`name`, `data` (base64), and `mime`. The existing message renderer already shows
`image/*` inline and `audio/*` as an `<audio>` player, so TTS output "just works."

### `logs`

Each `{level, message}` is written to the server log and shown as a toast. Levels:
`info` (accent), `success` (green), `error` (persists), `warning`.

### Errors

Set `"status": "error"` (plus `"error"`), OR return `{"error": "..."}`, OR exit non-zero
(stderr is surfaced). Anything already written (files, swipes) is kept.

# Triggers

A trigger fires an extension automatically instead of (or in addition to) the
manual toolbar button. The extension must be **enabled for the chat** and declare
the event in `triggers`. It must also apply to the target message's role (`roles`).

| Trigger | When | `target` |
|---|---|---|
| `manual` | Toolbar button | the clicked message |
| `generation_start` | A generation begins | the user message (or the slot being regenerated) |
| `generation_end` | A generation finishes [saving a reply] | the new assistant message |
| `edit` | A message is edited (new variant) | the edited message |
| `swipe` | Swiping to another variant | the swiped message |

Triggers run **fire-and-forget** on their own DB connection, so they never block
the request and a slow/failing extension won't break generation. They're a natural
fit for "rewrite every reply" — a `generation_end` extension returns
`{action: {type: "create_swipe"}}` and the reply is auto-improved as a swipe.

Take care: because they're user-supplied trusted code running unattended, an
enabled auto-trigger runs on *every* matching event. Don't enable a noisy one on
`swipe` unless that's what you want.

# Example — TTS

`extensions/tts.json`:

```json
{
  "name": "tts",
  "description": "Read the assistant reply aloud",
  "command": ["python3", "extensions/tts.py"],
  "timeout": 120,
  "category": "Voice",
  "roles": ["assistant"],
  "needs": ["message"],
  "params": [{"name": "voice", "type": "string", "default": "en-US"}]
}
```

`extensions/tts.py`:

```python
#!/usr/bin/env python3
import json, sys, base64, subprocess

req = json.load(sys.stdin)
text = "".join(s["content"] for s in req["target"]["segments"] if s["type"] == "text")
voice = req["config"].get("voice", "en-US")

# Whisper/edge-tts etc. — replace with your engine.
mp3 = subprocess.run(["edge-tts", "--voice", voice, "--text", text],
                     capture_output=True, check=True).stdout

print(json.dumps({
    "status": "done",
    "logs": [{"level": "success", "message": f"Spoke {len(text)} chars"}],
    "files": [{"name": "reply.mp3", "data": base64.b64encode(mp3).decode(), "mime": "audio/mpeg"}],
}))
```

# Example — Rewrite with a local model (llama.cpp text completion)

Targets [prose-rewriter-4b-v1.3](https://huggingface.co/chartreuse-verte/prose-rewriter-4b-v1.3)
via llama.cpp's raw **text completion** endpoint (`/completion`), *not* the OpenAI
compat route — its template uses `source`/`edit` roles no chat API models have. The
extension is wired to `generation_end` so every reply is auto-rewritten as a swipe.

The model breaks down on long input, so the sample never feeds a reply whole: it splits
into paragraphs (blank-line separated) and rewrites each sequentially, sub-chunks any single
paragraph over `max_chunk_chars` at **sentence boundaries**, and leaves fenced code blocks
untouched. Paragraph separators are preserved when it rejoins; set `split: false` for a
single whole-reply pass. Key config:

- `base_url` — llama.cpp server URL
- `mode` — `match` | `inflate` | `compress`
- `max_tokens`, `temperature`, `top_p` — completion params
- `min_words`, `min_bytes` — pass-through floor (the model pads/invents on short input)
- `max_chunk_chars` — split budget for a single rewrite call
- `split` — `true` to rewrite paragraph-by-paragraph, `false` for a single pass

See `extensions/samples/prose_rewriter.py` and `prose_rewriter.json` for the working
implementation.
