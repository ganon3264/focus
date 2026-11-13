#!/usr/bin/env bash
# Run tests with coverage.  Pass extra args, e.g. -k "test_name".
# Use --no-cov to skip coverage (just tests).
if command -v uv &>/dev/null; then
  # A .venv carried over from another machine/user points at an interpreter
  # this one cannot reach; uv errors out instead of rebuilding it.
  if [ -e ".venv" ] && ! [ -x ".venv/bin/python" ]; then rm -rf .venv; fi
  uv sync --locked --group dev
  RUNNER="uv run pytest"
else
  echo "UV not found, using regular python venv."
  if ! python -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 11) else 1)' 2>/dev/null; then
    echo >&2 "Error: Focus needs Python 3.11 or newer. Install uv (https://docs.astral.sh/uv/) or a newer Python."
    exit 1
  fi
  # A venv uv created has no pip, so it cannot be installed into.
  [ -x ".venv/bin/pip" ] || python -m venv --clear .venv
  .venv/bin/pip install --require-hashes -r requirements.lock.txt
  .venv/bin/pip install -e . --no-deps
  RUNNER=".venv/bin/pytest"
fi

if [[ "$*" == *"--no-cov"* ]]; then
  ARGS="${@/--no-cov/}"
  $RUNNER tests/ -v $ARGS
else
  $RUNNER tests/ -v --cov=focus --cov-report=term-missing --cov-report=html:tests/coverage_html "$@"
fi
