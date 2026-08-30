#!/usr/bin/env python3
"""Demo extension: rewrite a message to ALL CAPS by creating a new swipe.

Shows the write side of the contract. Replace the transform with a call to an
external model (using ``secrets`` + ``config``) for a real rewrite.
"""
import json
import sys

req = json.load(sys.stdin)
text = req["target"].get("content", "")

print(json.dumps({
    "status": "done",
    "action": {"type": "create_swipe", "content": text.upper()},
    "logs": [{"level": "success", "message": "Rewrote reply to ALL CAPS"}],
}))
