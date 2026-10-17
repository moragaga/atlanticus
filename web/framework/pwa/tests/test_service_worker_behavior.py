from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def test_service_worker_browser_behaviors() -> None:
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node.js is unavailable for service worker behavior tests')

    script = Path(__file__).with_name('test_service_worker.cjs')
    completed = subprocess.run(
        [node, '--test', str(script)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
