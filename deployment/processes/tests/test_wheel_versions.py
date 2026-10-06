from __future__ import annotations

import importlib.util
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

PROCESS_ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bundle = _load(PROCESS_ROOT / 'bundle.py', 'atlanticus_wheel_versions_bundle_test')
repo = _load(PROCESS_ROOT / 'wheel_repository.py', 'atlanticus_wheel_versions_repository_test')


def _wheel(
    path: Path,
    *,
    name: str = 'atlanticus-http',
    version: str = '1.0.0',
    dependencies: tuple[str, ...] = (),
    marker: str = 'original',
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = (
        'Metadata-Version: 2.3\n'
        f'Name: {name}\n'
        f'Version: {version}\n'
        'Requires-Python: ==3.14.2\n'
        + ''.join(f'Requires-Dist: {dependency}\n' for dependency in dependencies)
        + '\n'
    )
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr(f'{name.replace("-", "_")}-{version}.dist-info/METADATA', meta)
        archive.writestr('sample/__init__.py', marker)
    return path


def _project(
    root: Path,
    *,
    name: str,
    version: str = '1.0.0',
    dependencies: tuple[str, ...] = (),
    process: bool = False,
) -> Path:
    root.mkdir(parents=True)
    rendered = ''.join(f'    "{requirement}",\n' for requirement in dependencies)
    scripts = '\n[project.scripts]\nsample = "sample:main"\n' if process else ''
    container = (
        '\n[tool.atlanticus.container]\ncommand = "sample"\nsystem-profile = "base"\n'
        if process
        else ''
    )
    (root / 'pyproject.toml').write_text(
        '[build-system]\n'
        'requires = ["setuptools==83.0.0"]\n'
        'build-backend = "setuptools.build_meta"\n\n'
        '[project]\n'
        f'name = "{name}"\n'
        f'version = "{version}"\n'
        'requires-python = "==3.14.2"\n'
        'description = "Sample"\n'
        'dependencies = [\n'
        f'{rendered}'
        ']\n'
        f'{scripts}{container}',
        encoding='utf-8',
    )
    source = root / 'src/sample'
    source.mkdir(parents=True)
    (source / '__init__.py').write_text('VALUE = 1\n', encoding='utf-8')
    return root


def _fixture(tmp_path: Path):
    root = tmp_path / 'checkout'
    older = root / 'scopes/operational-data/processes/older'
    newer = root / 'scopes/operational-data/processes/newer'
    library = root / 'connectivity/http-client'
    _project(
        older,
        name='older-process',
        dependencies=('atlanticus-http==1.0.0',),
        process=True,
    )
    _project(
        newer,
        name='newer-process',
        dependencies=('atlanticus-http==1.1.0',),
        process=True,
    )
    _project(library, name='atlanticus-http', version='1.1.0')
    return root, older, newer


def test_repository_publication_is_idempotent_and_immutable(tmp_path: Path):
    store = repo.WheelRepository(tmp_path / 'published')
    wheel = _wheel(tmp_path / 'build' / 'atlanticus_http-1.0.0-py3-none-any.whl')

    first = store.publish(wheel)
    assert store.publish(wheel) == first
    assert store.resolve('atlanticus_http', '1.0.0') == first
    assert first.path.read_bytes() == wheel.read_bytes()

    replacement = _wheel(
        tmp_path / 'replacement' / wheel.name, marker='mutated-without-version-bump'
    )
    with pytest.raises(repo.WheelRepositoryError, match='immutable'):
        store.publish(replacement)
    assert store.resolve('atlanticus-http', '1.0.0') == first


def test_publication_cli_and_explicit_repository_location(tmp_path: Path, capsys):
    wheel = _wheel(tmp_path / 'build/atlanticus_http-1.0.0-py3-none-any.whl')
    location = tmp_path / 'durable-wheel-repository'
    assert repo.main(['publish', str(wheel), '--repository', str(location)]) == 0
    assert 'Published atlanticus-http==1.0.0' in capsys.readouterr().out
    assert repo.WheelRepository(location).resolve('atlanticus-http', '1.0.0')


def test_integrated_wheelhouse_is_default_and_external_override_is_rejected(
    tmp_path: Path, monkeypatch
):
    root = tmp_path / 'checkout'
    root.mkdir()
    monkeypatch.delenv(repo.REPOSITORY_ENVIRONMENT_VARIABLE, raising=False)
    assert repo.wheel_repository_path(root) == root / 'wheelhouse'
    monkeypatch.setenv(repo.REPOSITORY_ENVIRONMENT_VARIABLE, str(root / 'wheelhouse'))
    assert repo.wheel_repository_path(root) == root / 'wheelhouse'
    monkeypatch.setenv(repo.REPOSITORY_ENVIRONMENT_VARIABLE, str(tmp_path / 'external-wheels'))
    with pytest.raises(repo.WheelRepositoryError, match='must point to'):
        repo.wheel_repository_path(root)
    monkeypatch.delenv(repo.REPOSITORY_ENVIRONMENT_VARIABLE)
    (root / 'wheelhouse').symlink_to(tmp_path / 'external-wheels')
    with pytest.raises(repo.WheelRepositoryError, match='cannot be a symlink'):
        repo.wheel_repository_path(root)


def test_repository_detects_corruption_and_unsafe_release(tmp_path: Path):
    store = repo.WheelRepository(tmp_path / 'published')
    wheel = _wheel(tmp_path / 'build' / 'atlanticus_http-1.0.0-py3-none-any.whl')
    record = store.publish(wheel)
    record.path.write_bytes(b'tampered')
    with pytest.raises(repo.WheelRepositoryError, match='checksum mismatch'):
        store.resolve(record.name, record.version)


def test_per_process_versions_and_exact_missing_failure(tmp_path: Path):
    root, older, newer = _fixture(tmp_path)
    store = repo.WheelRepository(root / 'wheelhouse')
    archive = _wheel(tmp_path / 'wheels' / 'atlanticus_http-1.0.0-py3-none-any.whl')
    store.publish(archive)
    projects = bundle.discover_projects(root)

    older_sources, older_wheels, _ = bundle.resolve_bundle_dependencies(
        root, bundle.load_project(older), projects
    )
    newer_sources, newer_wheels, _ = bundle.resolve_bundle_dependencies(
        root, bundle.load_project(newer), projects
    )
    assert older_sources == ()
    assert [(item.name, item.version) for item in older_wheels] == [('atlanticus-http', '1.0.0')]
    assert [item.version for item in newer_sources] == ['1.1.0']
    assert newer_wheels == ()

    (root / 'wheelhouse/atlanticus-http/1.0.0/record.json').unlink()
    with pytest.raises(bundle.ProcessBundleError, match='record is invalid'):
        bundle.resolve_bundle_dependencies(root, bundle.load_project(older), projects)


def test_historical_transitives_and_conflicting_versions(tmp_path: Path):
    root, older, _ = _fixture(tmp_path)
    _project(root / 'backend/kernel', name='atlanticus-kernel', version='1.1.0')
    old_project = root / 'scopes/operational-data/processes/older/pyproject.toml'
    old_text = old_project.read_text(encoding='utf-8').replace(
        '"atlanticus-http==1.0.0",',
        '"atlanticus-http==1.0.0",\n    "atlanticus-kernel==1.0.0",',
    )
    old_project.write_text(old_text, encoding='utf-8')
    store = repo.WheelRepository(root / 'wheelhouse')
    store.publish(
        _wheel(
            tmp_path / 'wheels/atlanticus_http-1.0.0-py3-none-any.whl',
            dependencies=('atlanticus-kernel==1.0.0',),
        )
    )
    store.publish(
        _wheel(
            tmp_path / 'wheels/atlanticus_kernel-1.0.0-py3-none-any.whl',
            name='atlanticus-kernel',
        )
    )
    _, archive, _ = bundle.resolve_bundle_dependencies(
        root, bundle.load_project(older), bundle.discover_projects(root)
    )
    assert {item.name for item in archive} == {'atlanticus-http', 'atlanticus-kernel'}
    old_project.write_text(
        old_text.replace('"atlanticus-kernel==1.0.0",', '"atlanticus-kernel==1.1.0",'),
        encoding='utf-8',
    )
    with pytest.raises(bundle.ProcessBundleError, match='Conflicting internal versions'):
        bundle.resolve_bundle_dependencies(
            root, bundle.load_project(older), bundle.discover_projects(root)
        )


def test_fingerprint_tracks_historical_hash_and_receipt(tmp_path: Path):
    root, older, _ = _fixture(tmp_path)
    store = repo.WheelRepository(root / 'wheelhouse')
    record = store.publish(_wheel(tmp_path / 'wheels/atlanticus_http-1.0.0-py3-none-any.whl'))
    fingerprint = bundle.process_build_inputs_fingerprint(root, older)
    receipt = bundle.write_prepare_receipt(root, older, fingerprint)
    assert bundle.require_prepared_build_inputs(root, older) == receipt
    assert record.sha256 in (root / 'wheelhouse/atlanticus-http/1.0.0/record.json').read_text()
    record.path.write_bytes(b'corrupt')
    with pytest.raises(bundle.ProcessBundleError, match='checksum mismatch'):
        bundle.require_prepared_build_inputs(root, older)


def test_historical_process_fingerprint_ignores_newer_source_changes(tmp_path: Path):
    root, older, newer = _fixture(tmp_path)
    store = repo.WheelRepository(root / 'wheelhouse')
    store.publish(_wheel(tmp_path / 'wheels/atlanticus_http-1.0.0-py3-none-any.whl'))
    before_old = bundle.process_build_inputs_fingerprint(root, older)
    before_new = bundle.process_build_inputs_fingerprint(root, newer)

    source = root / 'connectivity/http-client/src/sample/__init__.py'
    source.write_text('VALUE = 2\n', encoding='utf-8')

    assert bundle.process_build_inputs_fingerprint(root, older) == before_old
    assert bundle.process_build_inputs_fingerprint(root, newer) != before_new


def test_bundle_copies_historical_wheel_with_own_lock(tmp_path: Path, monkeypatch):
    root, older, _ = _fixture(tmp_path)
    store = repo.WheelRepository(root / 'wheelhouse')
    archive = _wheel(tmp_path / 'wheels/atlanticus_http-1.0.0-py3-none-any.whl')
    store.publish(archive)

    def no_uv(command, *, cwd: Path):
        assert command[:2] == ('uv', 'lock')
        (cwd / 'uv.lock').write_text('# mocked uv lock\n', encoding='utf-8')

    monkeypatch.setattr(bundle, '_run', no_uv)
    old_bundle = bundle.build_process_bundle(
        repository_root=root,
        process_root=older,
        output_root=tmp_path / 'bundle',
        validate_installation=False,
    )
    assert (old_bundle / 'wheels' / archive.name).read_bytes() == archive.read_bytes()
    metadata = tomllib.loads((old_bundle / 'pyproject.toml').read_text())
    assert metadata['tool']['uv']['sources']['atlanticus-http'] == {
        'path': f'wheels/{archive.name}'
    }
    assert metadata['dependency-groups']['bundle-internal'] == ['atlanticus-http==1.0.0']


def test_catalog_discovers_all_wheelable_domains_not_workspace_or_generated(tmp_path: Path, capsys):
    root = tmp_path / 'checkout'
    entries = (
        ('backend/kernel', 'atlanticus-kernel'),
        ('connectivity/http-client', 'atlanticus-http'),
        ('integrations/pi/contracts', 'atlanticus-pi-contracts'),
        ('scopes/operational-data/processes/pi', 'operational-data-pi-process'),
        ('scopes/ada/web/kpis/collector', 'ada-web-kpi-collector'),
        ('web/capabilities/manager', 'atlanticus-web-manager'),
    )
    for relative, package in entries:
        _project(root / relative, name=package)
    (root / 'web/pyproject.toml').write_text(
        '[project]\nname = "atlanticus-web-workspace"\nversion = "0.1.0"\n',
        encoding='utf-8',
    )
    _project(root / 'wheelhouse/ignored', name='generated-package')
    _project(root / 'tooling/distribution/web/starter/ignored', name='template-package')

    discovered = repo.discover_wheel_projects(root)
    assert {item.name for item in discovered} == {name for _, name in entries}
    assert repo.main(['list', '--source-root', str(root)]) == 0
    result = capsys.readouterr().out
    assert 'Wheel projects: 6' in result
    assert 'web/capabilities/manager' in result
    assert 'scopes/operational-data/processes/pi' in result


def test_build_all_publishes_wheels_for_every_detected_project(tmp_path: Path, monkeypatch):
    from types import SimpleNamespace

    root = tmp_path / 'checkout'
    _project(root / 'backend/kernel', name='atlanticus-kernel')
    _project(root / 'web/capabilities/manager', name='atlanticus-web-manager')
    _project(
        root / 'scopes/operational-data/processes/pi',
        name='operational-data-pi-process',
    )
    repository = tmp_path / 'published'
    built: list[str] = []

    def fake_uv(command, *, cwd, check):
        assert command[:2] == ('uv', 'build') and '--wheel' in command and '--no-sources' in command
        metadata = tomllib.loads((Path(command[2]) / 'pyproject.toml').read_text())
        name, version = metadata['project']['name'], metadata['project']['version']
        built.append(name)
        output = Path(command[command.index('--out-dir') + 1])
        _wheel(output / f'{name.replace("-", "_")}-{version}-py3-none-any.whl', name=name)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(repo.subprocess, 'run', fake_uv)
    assert (
        repo.main(['build-all', '--source-root', str(root), '--repository', str(repository)]) == 0
    )
    assert set(built) == {
        'atlanticus-kernel',
        'atlanticus-web-manager',
        'operational-data-pi-process',
    }
    store = repo.WheelRepository(repository)
    for name in built:
        assert store.resolve(name, '1.0.0') is not None


def test_build_all_does_not_partially_publish_immutable_conflict(tmp_path: Path, monkeypatch):
    from types import SimpleNamespace

    root = tmp_path / 'checkout'
    _project(root / 'backend/alpha', name='atlanticus-alpha')
    _project(root / 'backend/zeta', name='atlanticus-zeta')
    store = repo.WheelRepository(tmp_path / 'published')
    store.publish(
        _wheel(
            tmp_path / 'old/atlanticus_zeta-1.0.0-py3-none-any.whl',
            name='atlanticus-zeta',
        )
    )

    def fake_uv(command, *, cwd, check):
        metadata = tomllib.loads((Path(command[2]) / 'pyproject.toml').read_text())
        name = metadata['project']['name']
        output = Path(command[command.index('--out-dir') + 1])
        _wheel(
            output / f'{name.replace("-", "_")}-1.0.0-py3-none-any.whl',
            name=name,
            marker='different-payload' if name == 'atlanticus-zeta' else 'original',
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(repo.subprocess, 'run', fake_uv)
    with pytest.raises(repo.WheelRepositoryError, match='immutable'):
        repo.build_and_publish_projects(root, store, repo.discover_wheel_projects(root))
    assert store.resolve('atlanticus-alpha', '1.0.0') is None


def test_wheel_catalog_rejects_duplicate_package_names(tmp_path: Path):
    root = tmp_path / 'checkout'
    _project(root / 'backend/first', name='atlanticus-shared')
    _project(root / 'connectivity/second', name='atlanticus_shared')
    with pytest.raises(repo.WheelRepositoryError, match='Duplicate wheel project'):
        repo.discover_wheel_projects(root)


def test_build_all_selects_named_subset_only(tmp_path: Path, monkeypatch):
    from types import SimpleNamespace

    root = tmp_path / 'checkout'
    _project(root / 'backend/kernel', name='atlanticus-kernel')
    _project(root / 'connectivity/http-client', name='atlanticus-http')
    built: list[str] = []

    def fake_uv(command, *, cwd, check):
        metadata = tomllib.loads((Path(command[2]) / 'pyproject.toml').read_text())
        name = metadata['project']['name']
        built.append(name)
        output = Path(command[command.index('--out-dir') + 1])
        _wheel(output / f'{name.replace("-", "_")}-1.0.0-py3-none-any.whl', name=name)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(repo.subprocess, 'run', fake_uv)
    assert (
        repo.main(
            [
                'build-all',
                '--source-root',
                str(root),
                '--repository',
                str(tmp_path / 'published'),
                '--select',
                'atlanticus-http',
            ]
        )
        == 0
    )
    assert built == ['atlanticus-http']
