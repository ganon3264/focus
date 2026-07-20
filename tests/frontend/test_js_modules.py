"""Run all Node-based unit tests for frontend JS modules."""

import subprocess
from pathlib import Path

import pytest

FRONTEND_DIR = Path(__file__).parent

JS_TEST_FILES = sorted(
    str(p.relative_to(FRONTEND_DIR))
    for p in FRONTEND_DIR.glob("test-*.js")
)


def _run_js_test(js_file: str):
    test_file = FRONTEND_DIR / js_file
    result = subprocess.run(["node", str(test_file)], capture_output=True, text=True)
    assert result.returncode == 0, (
        f"{js_file} failed:\n{result.stdout}\n{result.stderr}"
    )


@pytest.mark.parametrize("js_file", JS_TEST_FILES)
def test_js_module(js_file: str):
    _run_js_test(js_file)
