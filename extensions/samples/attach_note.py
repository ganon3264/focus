#!/usr/bin/env python3
"""Demo extension: attach a text note to the target message.

Shows the ``files`` side of the contract — a TTS extension would return an
``audio/mpeg`` entry here instead of ``text/plain``.
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
