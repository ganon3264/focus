@echo off
if "%FOCUS_HOST%"=="" set FOCUS_HOST=127.0.0.1
if "%FOCUS_PORT%"=="" set FOCUS_PORT=8000

if not exist ".git" goto :updated
choice /c yn /n /t 3 /d n /m "Update from git? [y/N] "
if errorlevel 2 goto :updated
git checkout --quiet master || goto :updated
git pull --ff-only || echo Update skipped - local changes or no upstream.
:updated

python vendor-sync.py --check || python vendor-sync.py
bin\tailwindcss-windows-x64 -i static\tailwind-input.css -o static\tailwind.css --minify

where uv >nul 2>nul
if %errorlevel% equ 0 (
    uv run python main.py --host=%FOCUS_HOST% --port=%FOCUS_PORT%
) else (
    echo UV not found, using regular python venv.
    if not exist ".venv" python -m venv .venv
    .venv\Scripts\pip install --require-hashes -r requirements.lock.txt
    .venv\Scripts\pip install -e . --no-deps
    .venv\Scripts\python main.py --host=%FOCUS_HOST% --port=%FOCUS_PORT%
)
