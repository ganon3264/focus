#!/usr/bin/env python3
"""Test fixture: rewrite a message to ALL CAPS by creating a new swipe.

Exercises the create_swipe write path. Not a shipped sample.
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
