# Espejo pedagógico: explica el gate del backend ADA sin cambiar su semántica.
from __future__ import annotations

import argparse
import ast
import platform
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile

EXPECTED_PYTHON_VERSION = '3.14.2'
LEGACY_PATTERN = re.compile(r'\b(?:KpiSource|KpiPartition|SourceRequirement)\b|ada\.data\.')


@dataclass(frozen=True, slots=True)
class Capability:
    key: str
    distribution: str
    import_name: str
    root: str
    dependencies: tuple[str, ...]


CAPABILITIES = {
    'kpi-core': Capability(
        'kpi-core',
        'ada-kpis-core',
        'ada.kpis.core',
        'kpis/core',
        ('atlanticus-operational-data-core==1.0.0',),
    ),
    'kpi-evaluation': Capability(
        'kpi-evaluation',
        'ada-kpis-evaluation',
        'ada.kpis.evaluation',
        'kpis/evaluation',
        ('ada-kpis-core==1.0.0', 'atlanticus-operational-data-core==1.0.0'),
    ),
    'kpi-persistence': Capability(
        'kpi-persistence',
        'ada-kpis-persistence',
        'ada.kpis.persistence',
        'kpis/persistence',
        ('ada-kpis-core==1.0.0', 'atlanticus-json==1.0.0', 'atlanticus-state==1.0.0'),
    ),
}

EXPECTED_SOURCES = {
    'ada-kpis-core': {'workspace': True},
    'ada-kpis-evaluation': {'workspace': True},
    'ada-kpis-persistence': {'workspace': True},
    'atlanticus-operational-data-core': {'path': '../../operational-data/core', 'editable': True},
    'atlanticus-json': {'path': '../../../backend/json', 'editable': True},
    'atlanticus-kernel': {'path': '../../../backend/kernel', 'editable': True},
    'atlanticus-observability': {'path': '../../../backend/observability', 'editable': True},
    'atlanticus-state': {'path': '../../../backend/state', 'editable': True},
}

LOCAL_BASELINES = {
    'atlanticus-operational-data-core': 'scopes/operational-data/core',
    'atlanticus-json': 'backend/json',
    'atlanticus-kernel': 'backend/kernel',
    'atlanticus-observability': 'backend/observability',
    'atlanticus-state': 'backend/state',
}


def _repo() -> Path:
    return Path(__file__).resolve().parents[4]


def _scope() -> Path:
    return _repo() / 'scopes/ada/backend'


def _run(command: list[str], *, cwd: Path) -> None:
    print('>', ' '.join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def _read(path: Path) -> dict[str, object]:
    with path.open('rb') as stream:
        return tomllib.load(stream)


def _project(path: Path) -> dict[str, object]:
    project = _read(path).get('project')
    if not isinstance(project, dict):
        raise SystemExit(f'Missing [project] table: {path}')
    return project


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Validate Atlanticus ADA backend capabilities.')
    parser.add_argument('capabilities', nargs='*')
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--list', action='store_true')
    return parser


def _selected(arguments: argparse.Namespace) -> tuple[Capability, ...]:
    if arguments.list:
        print('\n'.join(CAPABILITIES))
        raise SystemExit(0)
    requested = list(arguments.capabilities)
    if arguments.all and requested:
        raise SystemExit('Use --all or explicit capabilities, not both')
    if arguments.all or not requested:
        requested = list(CAPABILITIES)
    unknown = [item for item in requested if item not in CAPABILITIES]
    if unknown:
        raise SystemExit(f'Unknown ADA backend capabilities: {", ".join(unknown)}')
    return tuple(dict.fromkeys(CAPABILITIES[item] for item in requested))


def _validate_python() -> None:
    if platform.python_version() != EXPECTED_PYTHON_VERSION:
        raise SystemExit(
            f'Expected Python {EXPECTED_PYTHON_VERSION}, found {platform.python_version()}'
        )


def _validate_project(path: Path, distribution: str) -> None:
    project = _project(path / 'pyproject.toml')
    if project.get('name') != distribution or project.get('version') != '1.0.0':
        raise SystemExit(f'Unexpected project identity at {path}')


def _validate_workspace(repository: Path, scope: Path) -> None:
    document = _read(scope / 'pyproject.toml')
    project = document.get('project')
    if not isinstance(project, dict):
        raise SystemExit('Missing ADA backend workspace project')
    if project.get('name') != 'ada-backend-workspace' or project.get('version') != '1.0.0':
        raise SystemExit('Unexpected ADA backend workspace identity')
    uv = document.get('tool', {}).get('uv') if isinstance(document.get('tool'), dict) else None
    if not isinstance(uv, dict):
        raise SystemExit('Missing ADA backend UV workspace configuration')
    workspace = uv.get('workspace')
    if not isinstance(workspace, dict) or workspace.get('members') != [
        'kpis/core',
        'kpis/evaluation',
        'kpis/persistence',
    ]:
        raise SystemExit('ADA backend workspace members are not canonical')
    sources = uv.get('sources')
    if sources != EXPECTED_SOURCES:
        raise SystemExit('ADA backend workspace UV sources are not canonical')
    for distribution, value in EXPECTED_SOURCES.items():
        if not isinstance(value, dict) or 'path' not in value:
            continue
        target = (scope / str(value['path'])).resolve()
        try:
            target.relative_to(repository.resolve())
        except ValueError as error:
            raise SystemExit(f'{distribution} UV source escapes repository') from error
        if not (target / 'pyproject.toml').is_file():
            raise SystemExit(f'{distribution} source target is missing: {target}')
    for capability in CAPABILITIES.values():
        _validate_project(scope / capability.root, capability.distribution)
        dependencies = _project(scope / capability.root / 'pyproject.toml').get('dependencies')
        if tuple(dependencies or ()) != capability.dependencies:
            raise SystemExit(f'Unexpected dependencies for {capability.distribution}')
    for distribution, relative in LOCAL_BASELINES.items():
        _validate_project(repository / relative, distribution)


def _validate_ownership(repository: Path, scope: Path) -> None:
    if (repository / 'scopes/ada/kpis').exists():
        raise SystemExit(
            'Legacy scopes/ada/kpis authority must not coexist with ADA backend KPI domain'
        )
    core = scope / 'kpis/core/src/ada/kpis/core'
    if (core / 'requirements.py').exists() or (core / 'runtime.py').exists():
        raise SystemExit(
            'KPI Core must not recreate Operational Data requirements/runtime ownership'
        )
    for capability in CAPABILITIES.values():
        root = scope / capability.root
        for path in (root / 'src').rglob('*.py'):
            text = path.read_text(encoding='utf-8')
            if LEGACY_PATTERN.search(text.replace('KpiSourceTrace', '')):
                raise SystemExit(f'Legacy KPI data ownership found in {path}')


def _semantic_tree(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding='utf-8'))
    return ast.dump(tree, include_attributes=False)


def _validate_mirrors(scope: Path, repository: Path) -> None:
    for capability in CAPABILITIES.values():
        root = scope / capability.root
        productive = root / 'src'
        commented = root / 'commented'
        productive_files = {path.relative_to(productive) for path in productive.rglob('*.py')}
        commented_files = {path.relative_to(commented) for path in commented.rglob('*.py')}
        if productive_files != commented_files:
            raise SystemExit(f'Commented mirror file set mismatch for {capability.distribution}')
        for relative in productive_files:
            if _semantic_tree(productive / relative) != _semantic_tree(commented / relative):
                raise SystemExit(f'Commented mirror semantic mismatch: {relative}')
    productive_script = repository / 'scripts/scopes/ada/backend/check.py'
    commented_script = repository / 'scripts/commented/scopes/ada/backend/check.py'
    if _semantic_tree(productive_script) != _semantic_tree(commented_script):
        raise SystemExit('ADA backend gate Python mirror is not semantically equivalent')


def _run_tests(selected: tuple[Capability, ...], scope: Path) -> None:
    for capability in selected:
        print(f'[tests] {capability.key}', flush=True)
        _run([sys.executable, '-m', 'pytest', 'tests', '-ra'], cwd=scope / capability.root)


def _validate_imports(selected: tuple[Capability, ...], scope: Path) -> None:
    for capability in selected:
        _run([sys.executable, '-c', f'import {capability.import_name}'], cwd=scope)


def _build_wheels(selected: tuple[Capability, ...], scope: Path) -> None:
    dist = scope / 'dist'
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir(parents=True)
    for capability in selected:
        _run(['uv', 'build', capability.root, '--wheel', '--out-dir', str(dist)], cwd=scope)
        prefix = capability.distribution.replace('-', '_') + '-1.0.0-'
        wheels = tuple(path for path in dist.glob('*.whl') if path.name.startswith(prefix))
        if len(wheels) != 1:
            raise SystemExit(f'Expected exactly one wheel for {capability.distribution}')
        typed = capability.import_name.replace('.', '/') + '/py.typed'
        with ZipFile(wheels[0]) as archive:
            names = set(archive.namelist())
        if typed not in names:
            raise SystemExit(f'Missing py.typed in {capability.distribution} wheel')
        if any('/tests/' in name or '/commented/' in name for name in names):
            raise SystemExit(f'Non-productive files found in {capability.distribution} wheel')


def main() -> int:
    arguments = _parser().parse_args()
    selected = _selected(arguments)
    repository = _repo()
    scope = _scope()
    print('Atlanticus ADA backend capabilities:', ', '.join(item.key for item in selected))
    print('[1/10] Validating Python runtime')
    _validate_python()
    print('[2/10] Validating workspace and dependency correlation')
    _validate_workspace(repository, scope)
    print('[3/10] Validating ownership boundary')
    _validate_ownership(repository, scope)
    print('[4/10] Validating locked dependency graph')
    _run(['uv', 'lock', '--check'], cwd=scope)
    print('[5/10] Installing frozen workspace')
    _run(['uv', 'sync', '--frozen'], cwd=scope)
    targets = [item.root for item in selected]
    targets.extend(
        [
            str(repository / 'scripts/scopes/ada/backend/check.py'),
            str(repository / 'scripts/commented/scopes/ada/backend/check.py'),
        ]
    )
    print('[6/10] Applying safe Ruff fixes and validating formatting')
    _run([sys.executable, '-m', 'ruff', 'check', '--fix', *targets], cwd=scope)
    _run([sys.executable, '-m', 'ruff', 'format', *targets], cwd=scope)
    _run([sys.executable, '-m', 'ruff', 'check', *targets], cwd=scope)
    _run([sys.executable, '-m', 'ruff', 'format', '--check', *targets], cwd=scope)
    print('[7/10] Running capability tests')
    _run_tests(selected, scope)
    print('[8/10] Validating productive/commented semantic mirrors')
    _validate_mirrors(scope, repository)
    print('[9/10] Validating public imports')
    _validate_imports(selected, scope)
    print('[10/10] Building wheels')
    _build_wheels(selected, scope)
    print('Atlanticus ADA backend validated:', ', '.join(item.key for item in selected))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
