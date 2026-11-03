#!/usr/bin/env bash
set -euo pipefail

export FOCUS_DEBUG=1  # set this env var to enable debug logging

command -v python >/dev/null 2>&1 || { echo >&2 "Error: python is not installed or not on PATH."; exit 1; }

if [ -t 0 ] && [ -d .git ]; then
  reply=""
  read -r -t 3 -p "Update from git? [y/N] " reply || echo
  case "$reply" in
    [yY]*)
      git checkout --quiet master && git pull --ff-only \
        || echo "Update skipped — local changes or no upstream."
      ;;
  esac
fi

./vendor-sync.py --check || ./vendor-sync.py

./"$(./vendor-sync.py --print-tailwind-path)" -i static/tailwind-input.css -o static/tailwind.css --minify

if command -v uv &>/dev/null; then
  exec uv run python main.py --host "${FOCUS_HOST:-127.0.0.1}" --port "${FOCUS_PORT:-8000}"
else
  echo "UV not found, using regular python venv."
  [ -d ".venv" ] || python -m venv .venv
  .venv/bin/pip install --require-hashes -r requirements.lock.txt
  .venv/bin/pip install -e . --no-deps
  exec .venv/bin/python main.py --host "${FOCUS_HOST:-127.0.0.1}" --port "${FOCUS_PORT:-8000}"
fi
