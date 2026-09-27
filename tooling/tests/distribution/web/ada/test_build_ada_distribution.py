from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import shutil
import subprocess
import tomllib
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[4] / 'distribution/web/ada'
_TOOL = _ROOT / 'build_distribution.py'


def _load_tool(monkeypatch):
    wheels = ModuleType('build_wheelhouse')
    wheels.PYTHON_VERSION = '3.14.2'
    wheels.WheelhouseBuildError = RuntimeError
    wheels._require_python = lambda: None
    wheels._build_requirements = lambda _projects: ['setuptools==83.0.0']
    wheels._validate_starter = lambda _app, _profile: {
        'artifact_kind': 'web-application-starter',
        'profile': 'ada',
        'wheelhouse_included': False,
    }
    spec = importlib.util.spec_from_file_location('test_ada_delivery_tool', _TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'wheels', wheels)
    return module


def _hashed(name: str) -> str:
    return f'{name}==1.0.0 \\\n    --hash=sha256:{hashlib.sha256(name.encode()).hexdigest()}\n'


def test_hashed_requirements_reject_unpinned_or_unverified_registry_packages(tmp_path, monkeypatch):
    tool = _load_tool(monkeypatch)
    requirements = tmp_path / 'requirements.txt'
    requirements.write_text(_hashed('external'), encoding='utf-8')
    tool._validate_hashed_requirements(requirements)
    requirements.write_text('external>=1.0.0\n', encoding='utf-8')
    with pytest.raises(tool.AdaDistributionError, match='[Uu]npinned or unhashed|[Uu]nhashed distribution|[Ee]mpty or unhashed'):
        tool._validate_hashed_requirements(requirements)
    requirements.write_text('external==1.0.0\n', encoding='utf-8')
    with pytest.raises(tool.AdaDistributionError, match='[Uu]npinned or unhashed|[Uu]nhashed distribution|[Ee]mpty or unhashed'):
        tool._validate_hashed_requirements(requirements)
    requirements.write_text('-e ./private-project\n', encoding='utf-8')
    with pytest.raises(tool.AdaDistributionError, match='[Uu]npinned or unhashed|[Uu]nhashed distribution|[Ee]mpty or unhashed'):
        tool._validate_hashed_requirements(requirements)


def test_builder_packages_only_internals_and_locks_external_install_at_image_build(
    tmp_path, monkeypatch
):
    tool = _load_tool(monkeypatch)
    repo = tmp_path / 'repo'
    app = tmp_path / 'generated'
    app.mkdir()
    source = repo / 'scopes/ada/web/application/ada-generic-application'
    source.mkdir(parents=True)
    (source / 'uv.lock').write_text('test-lock', encoding='utf-8')
    monkeypatch.setattr(tool, 'REPOSITORY_ROOT', repo)

    def export(*, uv, project, staging):
        output = staging / 'external-runtime.txt'
        output.write_text(_hashed('external'), encoding='utf-8')
        constraints = staging / 'constraints.txt'
        constraints.write_text('external==1.0.0\n', encoding='utf-8')
        return output, constraints

    def host(*, uv, staging, constraints):
        assert constraints.name == 'constraints.txt'
        output = staging / 'host-runtime.txt'
        output.write_text(_hashed('gunicorn'), encoding='utf-8')
        return output

    def build_requirements(*, uv, staging, build_requirements):
        assert build_requirements == ['setuptools==83.0.0']
        output = staging / 'starter-build.txt'
        output.write_text(_hashed('setuptools'), encoding='utf-8')
        return output

    def internals(*, uv, project, target, staging):
        filename = 'ada_generic_application-0.2.17-py3-none-any.whl'
        wheel = target / filename
        wheel.write_bytes(b'fake-internal')
        return [{
            'name': 'ada-generic-application', 'version': '0.2.17',
            'filename': filename, 'sha256': tool._sha256(wheel),
        }]

    monkeypatch.setattr(tool, '_write_external_requirements', export)
    monkeypatch.setattr(tool, '_write_host_requirements', host)
    monkeypatch.setattr(tool, '_write_starter_build_requirements', build_requirements)
    monkeypatch.setattr(tool, '_build_internal', internals)
    real_run = subprocess.run

    def git_revision(command, **kwargs):
        if command[:3] == ['git', 'rev-parse', 'HEAD']:
            return SimpleNamespace(stdout='fixture-head\n')
        return real_run(command, **kwargs)

    monkeypatch.setattr(tool.subprocess, 'run', git_revision)
    result = tool.build_ada_distribution(application=app, uv='uv')
    assert result['status'] == 'BUILT_UNQUALIFIED'
    assert result['internal_wheels'] == 1
    assert list((app / 'wheelhouse').glob('*.whl'))[0].name.startswith('ada_generic_application')
    assert not (app / 'wheelhouse/external-1.0.0-py3-none-any.whl').exists()
    assert 'external==1.0.0' in (app / 'requirements/external-runtime.txt').read_text()
    assert 'gunicorn==1.0.0' in (app / 'requirements/host-runtime.txt').read_text()
    manifest = json.loads((app / 'wheelhouse/manifest.json').read_text())
    assert manifest['strategy'] == 'internal-wheels-external-image-build'
    assert manifest['requirements']['host-runtime.txt'] == tool._sha256(
        app / 'requirements/host-runtime.txt'
    )
    with pytest.raises(tool.AdaDistributionError, match='Regenerate'):
        tool.build_ada_distribution(application=app, uv='uv')


def test_internal_wheels_must_be_pure_python_for_portable_image(tmp_path, monkeypatch):
    tool = _load_tool(monkeypatch)
    source = tmp_path / 'package'
    source.mkdir()
    (source / 'pyproject.toml').write_text('[project]\nname="ada-internal"\nversion="1.0.0"\n')
    target = tmp_path / 'wheelhouse'
    target.mkdir()
    monkeypatch.setattr(tool, 'REPOSITORY_ROOT', tmp_path)
    wheels = tool.wheels
    wheels._active_packages = lambda exported: exported['packages']
    monkeypatch.setattr(tool, '_run', lambda command, *, cwd: None)
    wheels._read_toml = lambda path: (
        {'lock-version': '1.0', 'packages': [
            {'name': 'ada-generic-application', 'directory': {'path': '.'}},
        ]}
        if path.name == 'pylock.runtime.toml'
        else {'project': {'name': 'ada-internal', 'version': '1.0.0'}}
    )
    wheels._local_directory = lambda *args: source
    wheels._build_internal = lambda *args: 'ada_internal-1.0.0-cp314-cp314-macosx_14_0_arm64.whl'
    with pytest.raises(tool.AdaDistributionError, match='not portable'):
        tool._build_internal(uv='uv', project=source, target=target, staging=tmp_path)


def test_delivery_productive_and_commented_source_are_equivalent():
    productive = ast.dump(ast.parse(_TOOL.read_text()), include_attributes=False)
    commented = ast.dump(
        ast.parse((_ROOT / 'commented/build_distribution.py').read_text()),
        include_attributes=False,
    )
    assert productive == commented


def test_preflight_productive_and_commented_source_are_equivalent():
    source = _ROOT / 'qualify_distribution.py'
    annotated = _ROOT / 'commented/qualify_distribution.py'
    assert ast.dump(ast.parse(source.read_text()), include_attributes=False) == (
        ast.dump(ast.parse(annotated.read_text()), include_attributes=False)
    )


def test_uv_export_uses_supported_requirements_format_and_preserves_hashes(tmp_path, monkeypatch):
    tool = _load_tool(monkeypatch)
    commands = []

    def run(command, *, cwd):
        commands.append(command)
        output = Path(command[command.index('--output-file') + 1])
        output.write_text(
            'locked==1.0.0\n' if '--no-hashes' in command else _hashed('locked'),
            encoding='utf-8',
        )

    monkeypatch.setattr(tool, '_run', run)
    external, constraints = tool._write_external_requirements(
        uv='uv', project=tmp_path, staging=tmp_path
    )
    assert len(commands) == 2
    assert all(command[command.index('--format') + 1] == 'requirements.txt'
               for command in commands)
    assert '--locked' in commands[0] and '--no-emit-local' in commands[0]
    assert '--hash=sha256:' in external.read_text()
    assert '--hash=' not in constraints.read_text()


def test_uv_failure_reports_actionable_diagnostics_without_embedded_credentials(
    tmp_path, monkeypatch,
):
    tool = _load_tool(monkeypatch)
    monkeypatch.setattr(tool.subprocess, 'run', lambda *_args, **_kwargs: SimpleNamespace(
        returncode=2,
        stderr='error: unsupported format requirements-txt\nerror: registry https://secret@host.example',
    ))
    with pytest.raises(tool.AdaDistributionError) as error:
        tool._run(['uv', 'export'], cwd=tmp_path)
    message = str(error.value)
    assert 'unsupported format' in message
    assert 'secret@' not in message
    assert '[diagnostic redacted]' in message


def test_requirement_validation_supports_uv_multiline_output_and_rejects_invalid_hash(
    tmp_path, monkeypatch,
):
    tool = _load_tool(monkeypatch)
    path = tmp_path / 'requirements.txt'
    path.write_text(
        '# Created by uv export\n'
        + _hashed('first')
        + '    # via internal\n'
        + _hashed('second'), encoding='utf-8',
    )
    tool._validate_hashed_requirements(path)
    path.write_text('first==1.0.0 ' + chr(92) + '\n    --hash=sha256:bad\n', encoding='utf-8')
    with pytest.raises(tool.AdaDistributionError, match='Invalid SHA256'):
        tool._validate_hashed_requirements(path)


def test_failed_dependency_export_preserves_starter_and_never_creates_partial_output(
    tmp_path, monkeypatch,
):
    tool = _load_tool(monkeypatch)
    repo = tmp_path / 'repo'
    project = repo / 'scopes/ada/web/application/ada-generic-application'
    project.mkdir(parents=True)
    (project / 'uv.lock').write_text('fixture-lock')
    app = tmp_path / 'starter'
    app.mkdir()
    source = app / 'manifest.json'
    source.write_text('{"original":true}')
    monkeypatch.setattr(tool, 'REPOSITORY_ROOT', repo)
    monkeypatch.setattr(tool, '_write_external_requirements', lambda **_kw: (
        (_ for _ in ()).throw(tool.AdaDistributionError('uv export failed'))
    ))
    with pytest.raises(tool.AdaDistributionError, match='uv export failed'):
        tool.build_ada_distribution(application=app, uv='uv')
    assert source.read_text() == '{"original":true}'
    assert not (app / 'wheelhouse').exists()
    assert not (app / 'requirements').exists()
    assert not list(app.glob('.ada-delivery-*'))


@pytest.mark.skipif(shutil.which('uv') is None, reason='uv is required')
def test_real_uv_pylock_export_recognizes_filename_and_lists_local_packages(
    tmp_path, monkeypatch,
):
    tool = _load_tool(monkeypatch)
    project = tmp_path / 'local-app'
    local = project / 'internal'
    local.mkdir(parents=True)
    (project / 'pyproject.toml').write_text(
        '[project]\nname="ada-generic-application"\nversion="0.1.0"\n'
        'requires-python=">=3.11"\ndependencies=["sample-internal"]\n'
        '[build-system]\nrequires=["setuptools==83.0.0"]\n'
        'build-backend="setuptools.build_meta"\n'
        '[tool.uv.sources]\nsample-internal={path="internal"}\n',
        encoding='utf-8',
    )
    (local / 'pyproject.toml').write_text(
        '[project]\nname="sample-internal"\nversion="0.1.0"\n'
        'requires-python=">=3.11"\n'
        '[build-system]\nrequires=["setuptools==83.0.0"]\n'
        'build-backend="setuptools.build_meta"\n',
        encoding='utf-8',
    )
    uv = shutil.which('uv')
    subprocess.run(
        [uv, 'lock', '--project', str(project), '--offline'],
        cwd=project, check=True, capture_output=True, text=True,
    )
    tool.REPOSITORY_ROOT = tmp_path
    wheels = tool.wheels
    wheels._read_toml = lambda path: tomllib.loads(path.read_text(encoding='utf-8'))
    wheels._active_packages = lambda lock: lock['packages']
    wheels._local_directory = lambda package, base, _root: (
        base / package['directory']['path']
    ).resolve()

    def fake_build(_uv, source, target, name, version):
        filename = name.replace('-', '_') + f'-{version}-py3-none-any.whl'
        (target / filename).write_bytes(b'synthetic wheel')
        return filename

    wheels._build_internal = fake_build
    target = tmp_path / 'wheelhouse'
    target.mkdir()
    staging = tmp_path / 'staging'
    staging.mkdir()
    records = tool._build_internal(uv=uv, project=project, target=target, staging=staging)
    assert (staging / 'pylock.runtime.toml').is_file()
    assert {item['name'] for item in records} == {
        'ada-generic-application', 'sample-internal',
    }
