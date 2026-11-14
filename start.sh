#!/usr/bin/env bash
set -euo pipefail

# vendor-sync and the pip fallback below need a Python 3; uv does not (it brings
# its own), but the vendored dependency step runs before any of that.
PY="$(command -v python3 || command -v python || true)"
[ -n "$PY" ] || { echo >&2 "Error: Python 3 is not installed or not on PATH."; exit 1; }

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

"$PY" vendor-sync.py --check || "$PY" vendor-sync.py

./"$("$PY" vendor-sync.py --print-tailwind-path)" -i static/tailwind-input.css -o static/tailwind.css --minify

if command -v uv &>/dev/null; then
  # A .venv carried over from another machine/user points at an interpreter
  # this one cannot reach; uv errors out instead of rebuilding it.
  if [ -e ".venv" ] && ! [ -x ".venv/bin/python" ]; then rm -rf .venv; fi
  exec uv run python main.py --host "${FOCUS_HOST:-127.0.0.1}" --port "${FOCUS_PORT:-8000}"
else
  echo "UV not found, using regular python venv."
  if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 11) else 1)' 2>/dev/null; then
    echo >&2 "Error: Focus needs Python 3.11 or newer. Install uv (https://docs.astral.sh/uv/) or a newer Python."
    exit 1
  fi
  # A venv uv created has no pip, so it cannot be installed into.
  [ -x ".venv/bin/pip" ] || "$PY" -m venv --clear .venv
  .venv/bin/pip install --require-hashes -r requirements.lock.txt
  .venv/bin/pip install -e . --no-deps
  exec .venv/bin/python main.py --host "${FOCUS_HOST:-127.0.0.1}" --port "${FOCUS_PORT:-8000}"
fi
