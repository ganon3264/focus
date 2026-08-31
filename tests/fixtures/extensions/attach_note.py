#!/usr/bin/env python3
"""Test fixture: attach a text note to the target message.

Exercises the ``files`` attachment path. Not a shipped sample.
"""
import base64
import json
import sys

req = json.load(sys.stdin)
text = req["target"].get("content", "")
note = f"Note attached to: {text[:60]}"

print(json.dumps({
    "status": "done",
    "files": [{"name": "note.txt", "data": base64.b64encode(note.encode()).decode(), "mime": "text/plain"}],
    "logs": [{"level": "success", "message": "Attached a note"}],
}))
