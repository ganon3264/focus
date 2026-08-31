#!/usr/bin/env python3
"""Rewrite a message with the prose-rewriter-4b model via a llama.cpp server.

Talks to the raw **text completion** endpoint (``/completion``), not the OpenAI
compat route — the chat template here uses ``source``/``edit`` roles that no
OpenAI API models. The prompt string is built byte-for-byte from the model card.

The model breaks down on long input, so a reply is never passed through whole.
It is split into **paragraphs** (blank-line separated) and each is rewritten
sequentially; a paragraph that is itself over ``max_chunk_chars`` is sub-chunked
at sentence boundaries rather than fed whole. Fenced code blocks are left
verbatim (never fed to a prose rewriter). Paragraph structure is rejoined with
the original blank-line separators so the swipe reads like the source.

When the target carries segments, each ``text`` segment is rewritten in place and
the rebuilt list is returned via ``action.segments``, so the source's reasoning
and tool calls keep their exact position. When there are no segments, the whole
``content`` is rewritten and returned via ``action.content``.

On stdin: the extension request envelope. On stdout: the extension result JSON.
"""
import json
import re
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
# Soft budget for a single rewrite call. A reply longer than this is never fed
# whole — it's chunked so the model only ever sees a manageable passage.
max_chunk_chars = int(cfg.get("max_chunk_chars", 1500))
# Split long replies into paragraphs and rewrite sequentially. Off = one pass,
# which feeds the whole reply (code blocks included) in a single call.
split = cfg.get("split", True)

_calls = 0


def _rewrite(src: str) -> str:
    global _calls
    _calls += 1
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


def _is_code_block(block: str) -> bool:
    return re.search(r"^```", block, re.M) is not None


def _chunk_block(block: str, budget: int) -> list[str]:
    """Split one paragraph into pieces under ``budget`` chars.

    Prefers sentence boundaries so the model never sees a half sentence; falls
    back to word splitting only for a single runaway sentence that is itself
    over ``budget``.
    """
    if len(block) <= budget:
        return [block]
    sentences = re.split(r"(?<=[.!?])\s+", block)
    chunks: list[str] = []
    current = ""
    for sent in sentences:
        if not sent.strip():
            continue
        candidate = (current + " " + sent) if current else sent
        if current and len(candidate) > budget:
            chunks.append(current)
            current = sent
        else:
            current = candidate
    if current:
        chunks.append(current)

    final: list[str] = []
    for c in chunks:
        if len(c) <= budget:
            final.append(c)
            continue
        words = c.split(" ")
        cur = ""
        for w in words:
            candidate = (cur + " " + w) if cur else w
            if cur and len(candidate) > budget:
                final.append(cur)
                cur = w
            else:
                cur = candidate
        if cur:
            final.append(cur)
    return final or [block]


def _rewrite_block(block: str) -> str:
    block = block.strip()
    if not block or _is_code_block(block):
        return block
    parts = _chunk_block(block, max_chunk_chars)
    rewritten: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # The model pads/invents on short input — leave a tiny fragment alone.
        if len(part) < min_bytes or len(part.split()) < min_words:
            rewritten.append(part)
            continue
        rewritten.append(_rewrite(part) or part)
    return " ".join(rewritten)


def _rewrite_text(src: str) -> str:
    if not split:
        return _rewrite(src) or src
    parts = re.split(r"(\n\s*\n)", src)
    out: list[str] = []
    for i in range(0, len(parts), 2):
        block = parts[i] if i < len(parts) else ""
        sep = parts[i + 1] if i + 1 < len(parts) else ""
        out.append(_rewrite_block(block))
        out.append(sep)
    return "".join(out)


def _summary_log() -> list[dict]:
    if _calls == 0:
        return [{"level": "info", "message": "no text to rewrite — left unchanged"}]
    logs = [{"level": "success", "message": f"Rewrote reply ({mode}) with prose-rewriter"}]
    if _calls > 1:
        logs.insert(0, {"level": "info", "message": f"split into {_calls} passages"})
    return logs


def _pass_through(message: str) -> dict:
    if segments:
        return {
            "status": "done",
            "action": {"type": "create_swipe", "segments": segments},
            "logs": [{"level": "info", "message": message}],
        }
    return {
        "status": "done",
        "content": text,
        "logs": [{"level": "info", "message": message}],
    }


# The model pads and invents on short input (model card 'Input length');
# pass it through unchanged rather than fabricate.
if len(text) < min_bytes or len(text.split()) < min_words:
    print(json.dumps(_pass_through("input too short — left unchanged")))
    sys.exit(0)


if not segments:
    completion = _rewrite_text(text)
    if not completion:
        print(json.dumps({"status": "error", "error": "empty completion"}))
        sys.exit(0)
    print(json.dumps({
        "status": "done",
        "action": {"type": "create_swipe", "content": completion},
        "logs": _summary_log(),
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
        new_segments.append({"type": "text", "content": _rewrite_text(src) or src})
    else:
        new_segments.append(seg)

print(json.dumps({
    "status": "done",
    "action": {"type": "create_swipe", "segments": new_segments},
    "logs": _summary_log(),
}))
