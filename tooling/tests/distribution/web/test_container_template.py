from __future__ import annotations

import hashlib
import importlib.util
import json
import platform
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[3] / 'distribution/web'
_SPEC = importlib.util.spec_from_file_location('verify_starter_wheelhouse', _ROOT / 'starter/base/docker/verify_wheelhouse.py')
assert _SPEC is not None and _SPEC.loader is not None
_verifier = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_verifier)

_GEN_SPEC = importlib.util.spec_from_file_location('generate_web_starter_for_container', _ROOT / 'generate_starter.py')
assert _GEN_SPEC is not None and _GEN_SPEC.loader is not None
_generator = importlib.util.module_from_spec(_GEN_SPEC)
_GEN_SPEC.loader.exec_module(_generator)


@pytest.mark.parametrize('profile', ('generic', 'ada'))
def test_generated_starter_includes_offline_local_image_contract(tmp_path, monkeypatch, profile):
    if profile == 'ada':
        path = tmp_path / 'scopes/ada/web/application/ada-generic-application/.env.detail'
        path.parent.mkdir(parents=True)
        path.write_text('# Fixture\n', encoding='utf-8')
        monkeypatch.setattr(_generator, 'REPOSITORY_ROOT', tmp_path)
    output = _generator.generate_starter(profile=profile, destination=tmp_path / 'generated')
    dockerfile = (output / 'Dockerfile').read_text(encoding='utf-8')
    ignored = (output / '.dockerignore').read_text(encoding='utf-8')
    manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
    for path in ('Dockerfile', '.dockerignore', 'docker/verify_wheelhouse.py'):
        assert manifest['files'][path] == hashlib.sha256((output / path).read_bytes()).hexdigest()
    assert 'python:3.14.2-slim-bookworm' in dockerfile
    assert 'UV_OFFLINE=1' in dockerfile
    assert '--no-index --find-links /build/wheelhouse' in dockerfile
    assert 'USER app' in dockerfile
    assert 'exec python -m application' in dockerfile
    entrypoint = next(line.removeprefix('ENTRYPOINT ') for line in dockerfile.splitlines() if line.startswith('ENTRYPOINT '))
    assert json.loads(entrypoint)[:2] == ['/bin/sh', '-c']
    assert 'cannot run in production' in json.loads(entrypoint)[2]
    assert 'secrets.json' in ignored
    assert 'mapping-env.csv' in ignored
    assert 'wheelhouse/*.whl' in ignored


def _candidate(tmp_path: Path):
    root = tmp_path / 'starter'
    wheelhouse = root / 'wheelhouse'
    wheelhouse.mkdir(parents=True)
    wheel = wheelhouse / 'dummy-1.0.0-py3-none-any.whl'
    wheel.write_bytes(b'example wheel bytes')
    (root / 'manifest.json').write_text(
        json.dumps({'artifact_kind': 'web-application-starter', 'wheelhouse_included': True,
                    'profile': 'generic'}), encoding='utf-8'
    )
    payload = {'schema_version': 1, 'profile': 'generic', 'python': platform.python_version(),
               'platform': sys.platform, 'machine': platform.machine(),
               'packages': [{'filename': wheel.name,
                             'sha256': hashlib.sha256(wheel.read_bytes()).hexdigest()}]}
    (wheelhouse / 'manifest.json').write_text(json.dumps(payload), encoding='utf-8')
    return root, wheel


def test_image_preflight_verifies_offline_wheel_inventory(tmp_path):
    application, _wheel = _candidate(tmp_path)
    assert _verifier.verify_wheelhouse(application) == 1


def test_image_preflight_detects_changed_wheels(tmp_path):
    application, wheel = _candidate(tmp_path)
    wheel.write_bytes(b'tampered')
    with pytest.raises(_verifier.WheelhouseValidationError, match='integrity'):
        _verifier.verify_wheelhouse(application)


def test_image_preflight_rejects_mismatched_platform(tmp_path):
    application, _wheel = _candidate(tmp_path)
    manifest_path = application / 'wheelhouse/manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest['machine'] = 'unsupported-platform'
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    with pytest.raises(_verifier.WheelhouseValidationError, match='platform'):
        _verifier.verify_wheelhouse(application)
