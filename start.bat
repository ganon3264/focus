@echo off
if "%FOCUS_HOST%"=="" set FOCUS_HOST=127.0.0.1
if "%FOCUS_PORT%"=="" set FOCUS_PORT=8000

python vendor-sync.py --check || python vendor-sync.py
bin\tailwindcss-windows-x64 -i static\tailwind-input.css -o static\tailwind.css --minify

where uv >nul 2>nul
if %errorlevel% equ 0 (
    uv run python main.py --host=%FOCUS_HOST% --port=%FOCUS_PORT%
) else (
    echo UV not found, using regular python venv.
    if not exist ".venv" python -m venv .venv
    .venv\Scripts\pip install -e .
    .venv\Scripts\python main.py --host=%FOCUS_HOST% --port=%FOCUS_PORT%
)
