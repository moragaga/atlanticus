from __future__ import annotations

import os
import subprocess
import zipfile
from pathlib import Path

import pytest

_ROOT = Path(__file__).parents[1]
_PACKAGE = 'ada_command_center/processes/alarms_runtime/'
pytestmark = pytest.mark.skipif(
    os.environ.get('ATLANTICUS_QUALIFY_DISTRIBUTION') != '1',
    reason='Wheel build qualification is an explicit release gate',
)


def test_wheel_contains_executable_bootstrap_and_declares_runtime_dependencies(tmp_path: Path):
    subprocess.run(
        ['uv', 'build', '--wheel', '--no-sources', '--out-dir', str(tmp_path), str(_ROOT)],
        check=True,
        capture_output=True,
        text=True,
    )
    wheels = tuple(tmp_path.glob('ada_command_center_alarms_runtime_process-*.whl'))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as wheel:
        files = set(wheel.namelist())
        assert {
            f'{_PACKAGE}__main__.py',
            f'{_PACKAGE}application.py',
            f'{_PACKAGE}bootstrap.py',
            f'{_PACKAGE}settings.py',
        } <= files
        entrypoints_file = next(
            name for name in files if name.endswith('.dist-info/entry_points.txt')
        )
        assert (
            'ada-command-center-alarms-runtime = '
            'ada_command_center.processes.alarms_runtime.bootstrap:main'
        ) in wheel.read(entrypoints_file).decode('utf-8')
        metadata_file = next(name for name in files if name.endswith('.dist-info/METADATA'))
        metadata = wheel.read(metadata_file).decode('utf-8')
        assert 'Requires-Python: ==3.14.2' in metadata
        assert 'Requires-Dist: atlanticus-configuration==1.0.0' in metadata
        assert 'Requires-Dist: atlanticus-key-vault==1.0.0' in metadata
        assert 'Requires-Dist: atlanticus-observability-azure==1.0.0' in metadata
