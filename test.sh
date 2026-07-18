#!/usr/bin/env bash
# Run tests with coverage.  Pass extra args, e.g. -k "test_name".
# Use --no-cov to skip coverage (just tests).
if [[ "$*" == *"--no-cov"* ]]; then
  ARGS="${@/--no-cov/}"
  uv run pytest tests/ -v $ARGS
else
  uv run pytest tests/ -v --cov=focus --cov-report=term-missing --cov-report=html:tests/coverage_html "$@"
fi
