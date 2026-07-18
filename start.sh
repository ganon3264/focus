#!/usr/bin/env bash
set -euo pipefail

export FOCUS_DEBUG=1

command -v python >/dev/null 2>&1 || { echo >&2 "Error: python is not installed or not on PATH."; exit 1; }
command -v uv >/dev/null 2>&1 || { echo >&2 "Error: uv is not installed or not on PATH."; exit 1; }

./vendor-sync.py --check || ./vendor-sync.py

./bin/tailwindcss-linux-x64 -i static/tailwind-input.css -o static/tailwind.css --minify
exec uv run python main.py --host 0.0.0.0 --port 8000
