#!/usr/bin/env bash
set -euo pipefail

export FOCUS_DEBUG=1  # set this env var to enable debug logging

command -v python >/dev/null 2>&1 || { echo >&2 "Error: python is not installed or not on PATH."; exit 1; }
./vendor-sync.py --check || ./vendor-sync.py

./"$(./vendor-sync.py --print-tailwind-path)" -i static/tailwind-input.css -o static/tailwind.css --minify

if command -v uv &>/dev/null; then
  exec uv run python main.py --host "${FOCUS_HOST:-127.0.0.1}" --port "${FOCUS_PORT:-8000}"
else
  echo "UV not found, using regular python venv."
  [ -d ".venv" ] || python -m venv .venv
  .venv/bin/pip install -e .
  exec .venv/bin/python main.py --host "${FOCUS_HOST:-127.0.0.1}" --port "${FOCUS_PORT:-8000}"
fi
