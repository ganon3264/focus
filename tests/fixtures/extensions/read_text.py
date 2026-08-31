#!/usr/bin/env python3
"""Test fixture: read the ``text`` segments of the target message.

Exercises the read side of the contract. Not a shipped sample.
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
