#!/usr/bin/env python3
import subprocess
import json
import base64
import sys
import tempfile
import os


def capture(monitor: str = "current") -> bytes:
    mode_flag = {
        "current": "-m",
        "fullscreen": "-f",
        "activewindow": "-a",
    }.get(monitor, "-m")

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        subprocess.run(
            ["spectacle", mode_flag, "-b", "-n", "-o", tmp_path],
            check=True,
            capture_output=True,
            timeout=15,
        )
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def main():
    try:
        data = json.load(sys.stdin)
        monitor = data.get("monitor", "current")
    except (json.JSONDecodeError, KeyError):
        monitor = "current"

    try:
        png_bytes = capture(monitor)
        b64 = base64.b64encode(png_bytes).decode("ascii")
        print(json.dumps({
            "image": {
                "base64": b64,
                "mime": "image/png",
                "description": f"Screenshot ({monitor} monitor)",
            },
        }))
    except FileNotFoundError:
        print(json.dumps({"error": "spectacle not found — is KDE installed?"}))
    except subprocess.TimeoutExpired:
        print(json.dumps({"error": "spectacle timed out"}))
    except subprocess.CalledProcessError as e:
        msg = e.stderr.strip() or f"spectacle exited with code {e.returncode}"
        print(json.dumps({"error": msg}))
    except Exception as e:
        print(json.dumps({"error": str(e)}))


if __name__ == "__main__":
    main()
