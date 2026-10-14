from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from native_uv_sources import NativeUvSourceError, prepare_native_uv_sources


def _wheel(root: Path, name: str, version: str = '0.1.0', requires: tuple[str, ...] = ()) -> dict:
    filename = f'{name.replace("-", "_")}-{version}-py3-none-any.whl'
    destination = root / 'wheelhouse' / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    metadata = f'{name.replace("-", "_")}-{version}.dist-info'
    with zipfile.ZipFile(destination, 'w') as archive:
        dependencies = ''.join(f'Requires-Dist: {requirement}\n' for requirement in requires)
        archive.writestr(
            f'{metadata}/METADATA',
            f'Metadata-Version: 2.3\nName: {name}\nVersion: {version}\n{dependencies}',
        )
        archive.writestr(f'{metadata}/WHEEL', 'Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n')
        archive.writestr(f'{metadata}/RECORD', '')
    return {'name': name, 'filename': filename, 'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}


def _project(root: Path) -> Path:
    project = root / 'pyproject.toml'
    project.write_text(
        '[project]\nname="ada-integrated-operations-application"\nversion="0.1.0"\n'
        'requires-python=">=3.13"\n'
        'dependencies=["ada-generic-application==0.1.0"]\n'
        '[project.scripts]\nada-integrated-operations-application = "application:main"\n',
        encoding='utf-8',
    )
    return project


def test_uv_sources_are_relative_and_preserve_editable_root(tmp_path):
    project = _project(tmp_path)
    records = [_wheel(tmp_path, 'ada-generic-application'), _wheel(tmp_path, 'ada-project-tooling')]
    prepare_native_uv_sources(project, tmp_path / 'wheelhouse', records)
    metadata = tomllib.loads(project.read_text())
    sources = metadata['tool']['uv']['sources']
    assert sources['ada-generic-application']['path'].startswith('wheelhouse/')
    assert 'ada-project-tooling' not in sources
    assert metadata['project']['scripts']['ada-integrated-operations-application'] == 'application:main'
    assert 'constraint-dependencies' not in metadata['tool']['uv']
    assert 'uv.lock' not in {p.name for p in tmp_path.iterdir()}
    assert metadata['tool']['uv']['index'] == [
        {'name': 'atlanticus-wheelhouse', 'url': 'wheelhouse', 'format': 'flat'}
    ]


def test_corrupt_wheel_is_rejected_before_modifying_project(tmp_path):
    project = _project(tmp_path)
    previous = project.read_bytes()
    records = [_wheel(tmp_path, 'ada-generic-application')]
    records[0]['sha256'] = '0' * 64
    with pytest.raises(NativeUvSourceError, match='integrity'):
        prepare_native_uv_sources(project, tmp_path / 'wheelhouse', records)
    assert project.read_bytes() == previous


def test_duplicate_or_unmanaged_sources_are_rejected(tmp_path):
    project = _project(tmp_path)
    package = _wheel(tmp_path, 'ada-generic-application')
    with pytest.raises(NativeUvSourceError, match='Duplicate'):
        prepare_native_uv_sources(project, tmp_path / 'wheelhouse', [package, package])
    project.write_text(project.read_text() + '[tool.uv.sources]\n', encoding='utf-8')
    with pytest.raises(NativeUvSourceError, match='Existing uv'):
        prepare_native_uv_sources(project, tmp_path / 'wheelhouse', [package])


def test_uv_resolves_local_private_wheel_without_index(tmp_path):
    project = _project(tmp_path)
    package = _wheel(tmp_path, 'ada-generic-application')
    prepare_native_uv_sources(project, tmp_path / 'wheelhouse', [package])
    result = subprocess.run(
        ['uv', 'lock', '--offline', '--project', str(tmp_path)],
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    locked = (tmp_path / 'uv.lock').read_text()
    assert package['filename'] in locked



def test_uv_resolves_transitive_private_wheels_offline(tmp_path):
    project = _project(tmp_path)
    packages = [
        _wheel(tmp_path, 'ada-generic-application', requires=('ada-configuration-manager==0.1.0',)),
        _wheel(tmp_path, 'ada-configuration-manager', requires=('atlanticus-web-users==0.1.0',)),
        _wheel(tmp_path, 'atlanticus-web-users'),
    ]
    prepare_native_uv_sources(project, tmp_path / 'wheelhouse', packages)
    result = subprocess.run(
        ['uv', 'sync', '--offline', '--project', str(tmp_path)],
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    locked = (tmp_path / 'uv.lock').read_text()
    for name in ('ada-generic-application', 'ada-configuration-manager', 'atlanticus-web-users'):
        assert f'name = "{name}"' in locked
    installed = subprocess.run(
        ['uv', 'run', '--offline', '--project', str(tmp_path), 'python', '-c',
         'import importlib.metadata as m; print(m.version("ada-configuration-manager"))'],
        text=True, capture_output=True, check=False,
    )
    assert installed.returncode == 0, installed.stderr
    assert installed.stdout.strip() == '0.1.0'


def test_pedagogical_mirror_is_equivalent():
    source = ast.dump(ast.parse((ROOT / 'native_uv_sources.py').read_text()), include_attributes=False)
    mirror = ast.dump(ast.parse((ROOT / 'commented/native_uv_sources.py').read_text()), include_attributes=False)
    assert source == mirror
