#!/usr/bin/env python3
"""Rewrite a message with the prose-rewriter-4b model via a llama.cpp server.

Talks to the raw **text completion** endpoint (``/completion``), not the OpenAI
compat route — the chat template here uses ``source``/``edit`` roles that no
OpenAI API models. The prompt string is built byte-for-byte from the model card.

When the target carries segments, each ``text`` segment is rewritten in place and
the rebuilt list is returned via ``action.segments``, so the source's reasoning
and tool calls keep their exact position. When there are no segments, the whole
``content`` is rewritten and returned via ``action.content``.

On stdin: the extension request envelope. On stdout: the extension result JSON.
"""
import json
import sys
import urllib.request

req = json.load(sys.stdin)
cfg = req.get("config", {})
segments = req["target"].get("segments") or []
text = "".join(s.get("content", "") for s in segments if s.get("type") == "text").strip()
if not text:
    text = (req["target"].get("content") or "").strip()

base_url = (cfg.get("base_url") or "http://localhost:8080").rstrip("/")
mode = cfg.get("mode", "match")
max_tokens = int(cfg.get("max_tokens", 512))
temperature = float(cfg.get("temperature", 0.9))
top_p = float(cfg.get("top_p", 0.9))
min_words = int(cfg.get("min_words", 15))
min_bytes = int(cfg.get("min_bytes", 80))

# The model pads and invents on short input (see model card 'Input length');
# pass it through unchanged rather than fabricate.
if len(text) < min_bytes or len(text.split()) < min_words:
    print(json.dumps({
        "status": "done",
        "content": text,
        "logs": [{"level": "info", "message": "input too short — left unchanged"}],
    }))
    sys.exit(0)


def _rewrite(src: str) -> str:
    prompt = (
        "<|im_start|>source\n" + src + "<|im_end|>\n"
        "<|im_start|>edit\n" + mode + "<|im_end|>\n"
        "<|im_start|>rewrite\n"
    )
    body = {
        "prompt": prompt,
        "n_predict": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "stop": ["<|im_end|>"],
    }
    http_req = urllib.request.Request(
        base_url + "/completion",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(http_req, timeout=120) as resp:
        out = json.loads(resp.read())
    completion = (out.get("content") or "").strip()
    if completion.endswith("<|im_end|>"):
        completion = completion[: -len("<|im_end|>")].strip()
    return completion


if not segments:
    # Legacy / segment-less target: rewrite the whole content as one blob.
    completion = _rewrite(text)
    if not completion:
        print(json.dumps({"status": "error", "error": "empty completion"}))
        sys.exit(0)
    print(json.dumps({
        "status": "done",
        "action": {"type": "create_swipe", "content": completion},
        "logs": [{"level": "success", "message": f"Rewrote reply ({mode}) with prose-rewriter"}],
    }))
    sys.exit(0)

# Structured target (text interleaved with reasoning / tool calls): rewrite each
# text segment in place and return the rebuilt list so the source structure is
# preserved exactly. Non-text segments are kept verbatim.
new_segments = []
for seg in segments:
    if seg.get("type") == "text":
        src = seg.get("content", "")
        if not src.strip():
            new_segments.append(seg)
            continue
        rewritten = _rewrite(src)
        new_segments.append({"type": "text", "content": rewritten or src})
    else:
        new_segments.append(seg)

print(json.dumps({
    "status": "done",
    "action": {"type": "create_swipe", "segments": new_segments},
    "logs": [{"level": "success", "message": f"Rewrote reply ({mode}) with prose-rewriter"}],
}))
