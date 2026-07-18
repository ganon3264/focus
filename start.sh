#!/usr/bin/env bash
set -euo pipefail

./vendor-sync.py --check || ./vendor-sync.py

./bin/tailwindcss-linux-x64 -i static/tailwind-input.css -o static/tailwind.css --minify
exec uv run python main.py --host 0.0.0.0 --port 8000
