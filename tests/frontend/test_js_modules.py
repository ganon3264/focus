"""Run all Node-based unit tests for frontend JS modules."""

import subprocess
from pathlib import Path

FRONTEND_DIR = Path(__file__).parent


def _run_js_test(js_file: str):
    test_file = FRONTEND_DIR / js_file
    result = subprocess.run(["node", str(test_file)], capture_output=True, text=True)
    assert result.returncode == 0, (
        f"{js_file} failed:\n{result.stdout}\n{result.stderr}"
    )


def test_api_paths():
    _run_js_test("test_api_paths.js")


def test_message_renderer():
    _run_js_test("test_message_renderer.js")


def test_state_manager():
    _run_js_test("test_state_manager.js")


def test_extract_data():
    _run_js_test("test_extract_data.js")


def test_backup_manager():
    _run_js_test("test_backup_manager.js")
