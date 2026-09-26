from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

_TOOL = Path(__file__).resolve().parents[3] / 'distribution/web/qualify_starter.py'
_spec = importlib.util.spec_from_file_location('qualify_web_starter', _TOOL)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)


def _starter(root: Path, *, profile: str = 'generic', python: str = '==3.14.7') -> Path:
    root.mkdir(parents=True)
    (root / 'pyproject.toml').write_text(
        f'[project]\nname = "test-app"\nrequires-python = "{python}"\n',
        encoding='utf-8',
    )
    (root / 'src').mkdir()
    (root / 'src' / 'example.py').write_text('value = 1\n', encoding='utf-8')
    files = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in root.rglob('*') if p.is_file()}
    (root / 'manifest.json').write_text(json.dumps({
        'artifact_kind': 'web-application-starter', 'profile': profile,
        'qualification': 'UNVERIFIED', 'wheelhouse_included': False, 'files': files,
    }), encoding='utf-8')
    return root


def test_manifest_integrity_and_profile_are_validated(tmp_path):
    app = _starter(tmp_path / 'starter')
    assert _module.verify_manifest(app, 'generic') == []
    assert _module.verify_manifest(app, 'ada') == [
        'Generated application profile does not match qualification profile'
    ]
    (app / 'src/example.py').write_text('tampered = True\n', encoding='utf-8')
    assert 'Generated application file integrity failed: src/example.py' in (
        _module.verify_manifest(app, 'generic')
    )


def test_python_conflict_is_blocked_without_starting_app(tmp_path, monkeypatch):
    repo = tmp_path / 'repo'
    core = repo / 'web/framework/core/pyproject.toml'
    core.parent.mkdir(parents=True)
    core.write_text('[project]\nrequires-python = "==3.14.2"\n', encoding='utf-8')
    app = _starter(tmp_path / 'starter')
    monkeypatch.setattr(_module, 'REPOSITORY_ROOT', repo)
    monkeypatch.setattr(_module, 'run_probe', lambda **_kwargs: pytest.fail('Must not launch'))
    result = _module.qualify(application=app, profile='generic', python=tmp_path,
                             timeout=5, portable=False, inspect_only=False)
    assert result['status'] == 'BLOCKED'
    assert 'Conflicting Python requirements:' in result['errors'][0]
    assert 'starter: ==3.14.7' in result['errors'][0]
    assert 'atlanticus-web: ==3.14.2' in result['errors'][0]


def test_precheck_and_successful_probe_are_separate_evidence(tmp_path, monkeypatch):
    app = _starter(tmp_path / 'starter')
    monkeypatch.setattr(_module, 'REPOSITORY_ROOT', tmp_path / 'no-repository')
    result = _module.qualify(application=app, profile='generic', python=tmp_path,
                             timeout=5, portable=False, inspect_only=True)
    assert result['status'] == 'PRECHECK_PASS'
    assert result['runtime'] == 'UNVERIFIED'
    monkeypatch.setattr(_module, 'run_probe', lambda **_kwargs: {
        'status': 'PASS', 'checks': ['health.live', 'module.callback.http'],
    })
    result = _module.qualify(application=app, profile='generic', python=tmp_path,
                             timeout=5, portable=False, inspect_only=False)
    assert result['status'] == 'PASS'
    assert result['qualification'] == 'SOURCE_SMOKE'
    assert result['checks'] == ['health.live', 'module.callback.http']


def test_portable_mode_requires_wheelhouse(tmp_path, monkeypatch):
    app = _starter(tmp_path / 'starter')
    monkeypatch.setattr(_module, 'REPOSITORY_ROOT', tmp_path / 'no-repository')
    result = _module.qualify(application=app, profile='generic', python=tmp_path,
                             timeout=5, portable=True, inspect_only=True)
    assert result['status'] == 'BLOCKED'
    assert 'Portable qualification requires a populated wheelhouse' in result['errors']


def test_subprocess_result_is_parsed_without_trusting_other_stdout(tmp_path, monkeypatch):
    app = _starter(tmp_path / 'starter')
    fake = SimpleNamespace(
        stdout='Starting...\nSTARTER_QUALIFICATION_RESULT:{"status":"PASS","checks":["home.http"]}\n',
        stderr='', returncode=0,
    )
    monkeypatch.setattr(_module.subprocess, 'run', lambda *args, **kwargs: fake)
    result = _module.run_probe(python=tmp_path / 'python', profile='generic',
                               application=app, timeout=5, portable=False)
    assert result['status'] == 'PASS'
    assert result['checks'] == ['home.http']


def test_qualification_comment_mirrors_are_ast_equivalent():
    import ast

    product_root = _TOOL.parent
    for name in ('qualify_starter.py', 'probe_starter.py'):
        product = ast.dump(ast.parse((product_root / name).read_text()),
                           include_attributes=False)
        commented = ast.dump(ast.parse((product_root / 'commented' / name).read_text()),
                             include_attributes=False)
        assert product == commented


def test_portable_probe_creates_clean_environment_and_installs_offline(tmp_path, monkeypatch):
    app = _starter(tmp_path / 'starter')
    (app / 'wheelhouse').mkdir()
    (app / 'wheelhouse' / 'example.whl').write_bytes(b'test')
    monkeypatch.setattr(_module.shutil, 'which', lambda name: '/mock/uv')
    commands: list[list[str]] = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        if command[0] == '/mock/uv':
            return SimpleNamespace(stdout='', stderr='', returncode=0)
        return SimpleNamespace(
            stdout='STARTER_QUALIFICATION_RESULT:{"status":"PASS","checks":["example.http"]}\n',
            stderr='', returncode=0,
        )

    monkeypatch.setattr(_module.subprocess, 'run', fake_run)
    result = _module.run_probe(python=tmp_path / 'python', profile='generic',
                               application=app, timeout=5, portable=True)
    assert result['status'] == 'PASS'
    assert '--offline' in commands[0]
    assert '--no-index' in commands[1]
    assert '--find-links' in commands[1]
    assert '-e' in commands[1]
    assert '-I' in commands[2]
    assert '--portable' in commands[2]


def test_qualification_preserves_virtualenv_interpreter_symlink(tmp_path, monkeypatch):
    import os
    import subprocess
    import sys
    import venv

    venv_root = tmp_path / 'qualification-venv'
    venv.EnvBuilder(with_pip=False, symlinks=True).create(venv_root)
    interpreter = (
        venv_root / 'Scripts/python.exe' if os.name == 'nt'
        else venv_root / 'bin/python'
    )
    if not interpreter.is_symlink():
        pytest.skip('Virtual environment interpreter is not a symlink on this platform')
    assert interpreter.resolve() != interpreter.absolute()

    site = subprocess.check_output(
        [str(interpreter), '-I', '-c',
         "import sysconfig; print(sysconfig.get_path('purelib'))"],
        text=True,
    ).strip()
    dist = Path(site) / 'test_qualification-1.0.dist-info'
    dist.mkdir()
    (dist / 'METADATA').write_text(
        'Metadata-Version: 2.1\nName: test-qualification\nVersion: 1.0\n',
        encoding='utf-8',
    )
    observed = {}

    def run_probe(**kwargs):
        observed.update(kwargs)
        selected = kwargs['python']
        metadata_result = subprocess.check_output(
            [str(selected), '-I', '-c',
             "import sys; from importlib.metadata import version; "
             "print(sys.prefix); print(version('test-qualification'))"],
            text=True,
        ).splitlines()
        assert metadata_result == [str(venv_root), '1.0']
        return {'status': 'PASS', 'checks': ['venv.interpreter']}

    monkeypatch.setattr(_module, 'REPOSITORY_ROOT', tmp_path / 'no-repository')
    monkeypatch.setattr(_module, 'run_probe', run_probe)
    result = _module.qualify(
        application=_starter(tmp_path / 'starter'),
        profile='generic',
        python=interpreter,
        timeout=5,
        portable=False,
        inspect_only=False,
    )
    assert result['status'] == 'PASS'
    assert observed['python'] == interpreter.absolute()
