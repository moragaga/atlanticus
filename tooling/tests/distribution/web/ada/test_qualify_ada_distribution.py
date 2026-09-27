from __future__ import annotations

import hashlib
import importlib.util
import json
import platform
import shutil
import sys
from pathlib import Path
from types import ModuleType


_ROOT = Path(__file__).resolve().parents[4] / 'distribution/web/ada'
_TOOL = _ROOT / 'qualify_distribution.py'
_VERIFY = _ROOT.parent / 'starter/ada/docker/verify_delivery.py'


def _load_qualifier(monkeypatch):
    helper = ModuleType('build_distribution')

    def validate(path):
        text = path.read_text()
        if '==1.0' not in text or '--hash=sha256:' not in text:
            raise ValueError('Invalid external lock')

    helper._validate_hashed_requirements = validate
    monkeypatch.setitem(sys.modules, 'build_distribution', helper)
    spec = importlib.util.spec_from_file_location('ada_preflight_fixture', _TOOL)
    assert spec is not None and spec.loader is not None
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    return tool


def _candidate(tmp_path):
    app = tmp_path / 'ada'
    (app / 'docker').mkdir(parents=True)
    shutil.copyfile(_VERIFY, app / 'docker/verify_delivery.py')
    wheelhouse = app / 'wheelhouse'
    wheelhouse.mkdir()
    wheel = wheelhouse / 'ada_generic_application-0.2.17-py3-none-any.whl'
    wheel.write_bytes(b'wheel')
    req = app / 'requirements'
    req.mkdir()
    locks = {}
    for name in ('external-runtime.txt', 'host-runtime.txt', 'starter-build.txt'):
        path = req / name
        path.write_text('locked==1.0 \\\n    --hash=sha256:' + 'a' * 64 + '\n')
        locks[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    strategy = 'internal-wheels-external-image-build'
    wheel_manifest = {
        'schema_version': 2, 'strategy': strategy,
        'profile': 'ada', 'python': platform.python_version(),
        'requirements': locks,
        'packages': [{
            'filename': wheel.name, 'sha256': hashlib.sha256(wheel.read_bytes()).hexdigest(),
        }],
    }
    (wheelhouse / 'manifest.json').write_text(json.dumps(wheel_manifest))
    files = {'docker/verify_delivery.py': hashlib.sha256((app / 'docker/verify_delivery.py').read_bytes()).hexdigest()}
    starter_manifest = {
        'artifact_kind': 'web-application-starter', 'profile': 'ada',
        'wheelhouse_included': True, 'delivery_strategy': strategy, 'files': files,
    }
    (app / 'manifest.json').write_text(json.dumps(starter_manifest))
    return app


def test_preflight_validates_source_and_distribution_without_starting_container(tmp_path, monkeypatch):
    tool = _load_qualifier(monkeypatch)
    app = _candidate(tmp_path)
    result = tool.qualify_ada_distribution(app)
    assert result['status'] == 'PRECHECK_PASS'
    assert result['image_build'] == 'UNVERIFIED'
    assert result['runtime'] == 'UNVERIFIED'
    (app / 'docker/verify_delivery.py').write_text('tampered')
    result = tool.qualify_ada_distribution(app)
    assert result['status'] == 'BLOCKED'
    assert 'source integrity' in result['error']


def test_preflight_rejects_tampered_external_requirements(tmp_path, monkeypatch):
    tool = _load_qualifier(monkeypatch)
    app = _candidate(tmp_path)
    (app / 'requirements/external-runtime.txt').write_text('changed')
    result = tool.qualify_ada_distribution(app)
    assert result['status'] == 'BLOCKED'
    assert 'requirements integrity' in result['error']
