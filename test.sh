#!/usr/bin/env bash
# Run tests with coverage.  Pass extra args, e.g. -k "test_name".
# Use --no-cov to skip coverage (just tests).
if command -v uv &>/dev/null; then
  RUNNER="uv run pytest"
else
  echo "UV not found, using regular python venv."
  [ -d ".venv" ] || python -m venv .venv
  .venv/bin/pip install -e .
  RUNNER=".venv/bin/pytest"
fi

if [[ "$*" == *"--no-cov"* ]]; then
  ARGS="${@/--no-cov/}"
  $RUNNER tests/ -v $ARGS
else
  $RUNNER tests/ -v --cov=focus --cov-report=term-missing --cov-report=html:tests/coverage_html "$@"
fi
