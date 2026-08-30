#!/usr/bin/env python3
"""Demo extension: read the ``text`` segments of the target message.

This is the read side of the contract — no model, no network. Swap the body
for a real TTS engine (edge-tts, etc.) and return a ``files`` entry for audio.
"""
import json
import sys

req = json.load(sys.stdin)
segments = req["target"].get("segments") or []
text = " ".join(s.get("content", "") for s in segments if s.get("type") == "text").strip()

print(json.dumps({
    "status": "done",
    "content": text,
    "logs": [{"level": "success", "message": f"Read {len(text)} characters"}],
}))
