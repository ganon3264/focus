#!/usr/bin/env python3
"""Rewrite a message with the prose-rewriter-4b model via a llama.cpp server.

Talks to the raw **text completion** endpoint (``/completion``), not the OpenAI
compat route — the chat template here uses ``source``/``edit`` roles that no
OpenAI API models. The prompt string is built byte-for-byte from the model card.

On stdin: the extension request envelope. On stdout: the extension result JSON.
"""
import json
import sys
import urllib.request

req = json.load(sys.stdin)
cfg = req.get("config", {})
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

prompt = (
    "<|im_start|>source\n" + text + "<|im_end|>\n"
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

try:
    with urllib.request.urlopen(http_req, timeout=120) as resp:
        out = json.loads(resp.read())
except Exception as e:
    # Surface the reason to the toast; anything already written is kept.
    print(json.dumps({"status": "error", "error": f"llama.cpp request failed: {e}"}))
    sys.exit(0)

completion = (out.get("content") or "").strip()
if completion.endswith("<|im_end|>"):
    completion = completion[: -len("<|im_end|>")].strip()

if not completion:
    print(json.dumps({"status": "error", "error": "empty completion"}))
    sys.exit(0)

print(json.dumps({
    "status": "done",
    "action": {"type": "create_swipe", "content": completion},
    "logs": [{"level": "success", "message": f"Rewrote reply ({mode}) with prose-rewriter"}],
}))
