#!/usr/bin/env bash
./bin/tailwindcss-linux-x64 -i static/tailwind-input.css -o static/tailwind.css --minify
PYVERN_DEBUG=1 uv run python main.py --host 0.0.0.0 --port 8000
