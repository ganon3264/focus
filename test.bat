@echo off
where uv >nul 2>nul
if %errorlevel% equ 0 (
    uv sync --group dev
    uv run pytest tests/ -v --cov=focus --cov-report=term-missing %*
) else (
    echo UV not found, using regular python venv.
    if not exist ".venv" python -m venv .venv
    .venv\Scripts\pip install -e ".[test]"
    .venv\Scripts\pytest tests/ -v --cov=focus --cov-report=term-missing %*
)
