#!/usr/bin/env python3
"""Test fixture: return a file with ``attach: false`` — the play-only path.

Exercises the ``attach`` flag on the result contract. Not a shipped sample.
"""

import base64
import json
import sys

req = json.load(sys.stdin)
text = req["target"].get("content", "")
note = f"Play note for: {text[:40]}"

print(
    json.dumps(
        {
            "status": "done",
            "attach": False,
            "files": [{"name": "note.txt", "data": base64.b64encode(note.encode()).decode(), "mime": "text/plain"}],
            "logs": [{"level": "success", "message": "Prepared a play-only note"}],
        }
    )
)
