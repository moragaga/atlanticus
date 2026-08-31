from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile

EXPECTED_PYTHON_VERSION = '3.14.2'


@dataclass(frozen=True, slots=True)
class OperationalDataCapability:
    key: str
    distribution: str
    import_name: str
    project_root: str
    source_root: str
    commented_root: str


CAPABILITIES: dict[str, OperationalDataCapability] = {
    'core': OperationalDataCapability(
        'core',
        'atlanticus-operational-data-core',
        'atlanticus.operational_data.core',
        'core',
        'core/src',
        'core/commented',
    ),
    'planner': OperationalDataCapability(
        'planner',
        'atlanticus-operational-data-planner',
        'atlanticus.operational_data.planner',
        'planner',
        'planner/src',
        'planner/commented',
    ),
    'calendar': OperationalDataCapability(
        'calendar',
        'atlanticus-operational-data-calendar',
        'atlanticus.operational_data.calendar',
        'calendar',
        'calendar/src',
        'calendar/commented',
    ),
    'sources': OperationalDataCapability(
        'sources',
        'atlanticus-operational-data-sources',
        'atlanticus.operational_data.sources',
        'sources',
        'sources/src',
        'sources/commented',
    ),
}

EXPECTED_WORKSPACE_SOURCES = {
    'atlanticus-operational-data-core': {'workspace': True},
    'atlanticus-operational-data-planner': {'workspace': True},
    'atlanticus-operational-data-calendar': {'workspace': True},
    'atlanticus-operational-data-sources': {'workspace': True},
    'atlanticus-datasets': {'path': '../../backend/datasets', 'editable': True},
}

EXPECTED_DEPENDENCIES = {
    'core': [],
    'planner': ['atlanticus-operational-data-core==1.0.0'],
    'calendar': [],
    'sources': [
        'atlanticus-operational-data-calendar==1.0.0',
        'atlanticus-operational-data-core==1.0.0',
        'atlanticus-operational-data-planner==1.0.0',
        'atlanticus-datasets==1.0.0',
        'pandas==3.0.3',
        'pyarrow==25.0.0',
    ],
}

LEGACY_TOKENS = (
    'ada.data.',
    'ada.operational_calendar',
    'ada-operational-data-',
    'ada-operational-calendar',
    'ADA_OPERATIONAL_CALENDARS',
)


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _scope_root() -> Path:
    return _repository_root() / 'scopes/operational-data'


def _run(command: list[str], *, cwd: Path) -> None:
    print('>', ' '.join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Validate Atlanticus Operational Data capabilities.'
    )
    parser.add_argument('capabilities', nargs='*')
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--list', action='store_true')
    return parser


def _resolve_capabilities(arguments: argparse.Namespace) -> tuple[OperationalDataCapability, ...]:
    if arguments.list:
        for key in CAPABILITIES:
            print(key)
        raise SystemExit(0)
    requested = list(arguments.capabilities)
    if arguments.all and requested:
        raise SystemExit('Use --all or explicit capabilities, not both')
    if arguments.all or not requested:
        requested = list(CAPABILITIES)
    unknown = [key for key in requested if key not in CAPABILITIES]
    if unknown:
        raise SystemExit(
            f'Unknown Operational Data capabilities: {", ".join(unknown)}. '
            f'Valid capabilities: {", ".join(CAPABILITIES)}'
        )
    seen: set[str] = set()
    resolved: list[OperationalDataCapability] = []
    for key in requested:
        if key not in seen:
            resolved.append(CAPABILITIES[key])
            seen.add(key)
    return tuple(resolved)


def _read_toml(path: Path) -> dict[str, object]:
    with path.open('rb') as stream:
        return tomllib.load(stream)


def _project(path: Path) -> dict[str, object]:
    project = _read_toml(path).get('project')
    if not isinstance(project, dict):
        raise SystemExit(f'Missing [project] table: {path}')
    return project


def _validate_python() -> None:
    found = platform.python_version()
    if found != EXPECTED_PYTHON_VERSION:
        raise SystemExit(f'Expected Python {EXPECTED_PYTHON_VERSION}, found {found}')


def _validate_workspace(scope: Path, repository: Path) -> None:
    document = _read_toml(scope / 'pyproject.toml')
    project = document.get('project')
    if (
        not isinstance(project, dict)
        or project.get('name') != 'atlanticus-operational-data-workspace'
    ):
        raise SystemExit('Unexpected Operational Data workspace identity')
    if project.get('version') != '1.0.0':
        raise SystemExit('Operational Data workspace must be version 1.0.0')
    tool = document.get('tool')
    if not isinstance(tool, dict):
        raise SystemExit('Missing [tool] configuration in Operational Data workspace')
    ruff = tool.get('ruff')
    if not isinstance(ruff, dict):
        raise SystemExit('Missing [tool.ruff] configuration in Operational Data workspace')
    excluded = ruff.get('extend-exclude', [])
    if not isinstance(excluded, list) or any('commented' in str(pattern) for pattern in excluded):
        raise SystemExit('Operational Data workspace Ruff must include commented mirrors')
    for capability in CAPABILITIES.values():
        capability_document = _read_toml(scope / capability.project_root / 'pyproject.toml')
        capability_tool = capability_document.get('tool')
        if not isinstance(capability_tool, dict):
            raise SystemExit(f'Missing [tool] configuration for {capability.distribution}')
        capability_ruff = capability_tool.get('ruff')
        if not isinstance(capability_ruff, dict):
            raise SystemExit(f'Missing [tool.ruff] configuration for {capability.distribution}')
        for key in ('exclude', 'extend-exclude'):
            patterns = capability_ruff.get(key, [])
            if isinstance(patterns, str):
                patterns = [patterns]
            if not isinstance(patterns, list):
                raise SystemExit(f'Invalid Ruff {key} for {capability.distribution}')
            if any('commented' in str(pattern) for pattern in patterns):
                raise SystemExit(f'{capability.distribution} Ruff must include commented mirrors')
    uv = tool.get('uv')
    if not isinstance(uv, dict):
        raise SystemExit('Missing [tool.uv] configuration in Operational Data workspace')
    workspace = uv.get('workspace')
    expected_members = ['core', 'planner', 'calendar', 'sources']
    if not isinstance(workspace, dict) or workspace.get('members') != expected_members:
        raise SystemExit('Operational Data workspace members are not canonical')
    sources = uv.get('sources')
    if not isinstance(sources, dict):
        raise SystemExit('Missing [tool.uv.sources] in Operational Data workspace')
    for distribution, expected in EXPECTED_WORKSPACE_SOURCES.items():
        source = sources.get(distribution)
        if source != expected:
            raise SystemExit(f'Unexpected UV source for {distribution}: {source!r}')
    dataset_target = (scope / '../../backend/datasets').resolve()
    try:
        dataset_target.relative_to(repository.resolve())
    except ValueError as exc:
        raise SystemExit('atlanticus-datasets UV source escapes repository') from exc
    if not (dataset_target / 'pyproject.toml').is_file():
        raise SystemExit(f'atlanticus-datasets source target is missing: {dataset_target}')


def _require_version(project_root: Path, distribution: str, expected: str) -> None:
    project = _project(project_root / 'pyproject.toml')
    if project.get('name') != distribution:
        raise SystemExit(f'Unexpected distribution at {project_root}: {project.get("name")!r}')
    if project.get('version') != expected:
        raise SystemExit(f'{distribution} must be version {expected}')


def _validate_dependency_correlation(scope: Path, repository: Path) -> None:
    for capability in CAPABILITIES.values():
        project_root = scope / capability.project_root
        _require_version(project_root, capability.distribution, '1.0.0')
        project = _project(project_root / 'pyproject.toml')
        dependencies = project.get('dependencies')
        if dependencies != EXPECTED_DEPENDENCIES[capability.key]:
            raise SystemExit(
                f'Unexpected dependencies for {capability.distribution}: {dependencies!r}'
            )
    _require_version(repository / 'backend/datasets', 'atlanticus-datasets', '1.0.0')


def _validate_ownership(scope: Path) -> None:
    roots = [
        scope / capability.project_root / relative
        for capability in CAPABILITIES.values()
        for relative in ('src', 'commented', 'tests')
    ]
    for root in roots:
        for path in root.rglob('*'):
            if not path.is_file() or path.suffix not in {'.py', '.toml'}:
                continue
            text = path.read_text(encoding='utf-8')
            for token in LEGACY_TOKENS:
                if token in text:
                    raise SystemExit(f'Legacy ADA ownership token {token!r} found in {path}')


def _run_tests(capabilities: tuple[OperationalDataCapability, ...], scope: Path) -> None:
    for capability in capabilities:
        print(f'[tests] {capability.key}', flush=True)
        _run([sys.executable, '-m', 'pytest', 'tests'], cwd=scope / capability.project_root)


def _validate_mirrors(
    capabilities: tuple[OperationalDataCapability, ...],
    scope: Path,
    repository: Path,
) -> None:
    arguments: list[str] = []
    for capability in capabilities:
        arguments.extend([capability.source_root, capability.commented_root])
    arguments.extend(
        [
            str(repository / 'scripts/scopes/operational-data'),
            str(repository / 'scripts/commented/scopes/operational-data'),
        ]
    )
    _run(
        [
            sys.executable,
            str(repository / 'scripts/repository/validate_mirrors.py'),
            *arguments,
        ],
        cwd=scope,
    )


def _validate_imports(capabilities: tuple[OperationalDataCapability, ...], scope: Path) -> None:
    for capability in capabilities:
        _run([sys.executable, '-c', f'import {capability.import_name}'], cwd=scope)


def _build_wheels(capabilities: tuple[OperationalDataCapability, ...], scope: Path) -> None:
    dist = scope / 'dist'
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir(parents=True)
    for capability in capabilities:
        _run(
            ['uv', 'build', capability.project_root, '--wheel', '--out-dir', str(dist)],
            cwd=scope,
        )
        prefix = capability.distribution.replace('-', '_') + '-1.0.0-'
        wheels = tuple(path for path in dist.glob('*.whl') if path.name.startswith(prefix))
        if len(wheels) != 1:
            raise SystemExit(
                f'Expected one wheel for {capability.distribution}, found {len(wheels)}'
            )
        typed_path = capability.import_name.replace('.', '/') + '/py.typed'
        with ZipFile(wheels[0]) as archive:
            names = set(archive.namelist())
        if typed_path not in names:
            raise SystemExit(f'Missing py.typed in wheel: {capability.distribution}')
        if any('/tests/' in name or '/commented/' in name for name in names):
            raise SystemExit(f'Non-productive files found in wheel: {capability.distribution}')


def main() -> int:
    arguments = _parser().parse_args()
    capabilities = _resolve_capabilities(arguments)
    repository = _repository_root()
    scope = _scope_root()
    print('Atlanticus Operational Data capabilities:', ', '.join(item.key for item in capabilities))
    print('[1/10] Validating Python runtime')
    _validate_python()
    print('[2/10] Validating scope workspace composition')
    _validate_workspace(scope, repository)
    print('[3/10] Validating dependency and version correlation')
    _validate_dependency_correlation(scope, repository)
    print('[4/10] Validating ownership boundary and retired ADA namespaces')
    _validate_ownership(scope)
    print('[5/10] Validating locked dependency graph')
    _run(['uv', 'lock', '--check'], cwd=scope)
    targets = [capability.project_root for capability in capabilities]
    targets.extend(
        [
            str(repository / 'scripts/scopes/operational-data/check.py'),
            str(repository / 'scripts/commented/scopes/operational-data/check.py'),
            str(repository / 'scripts/repository/validate_mirrors.py'),
            str(repository / 'scripts/commented/repository/validate_mirrors.py'),
        ]
    )
    print('[6/10] Applying safe Ruff fixes and formatting')
    _run(['ruff', 'check', '--fix', *targets], cwd=scope)
    _run(['ruff', 'format', *targets], cwd=scope)
    _run(['ruff', 'check', *targets], cwd=scope)
    _run(['ruff', 'format', '--check', *targets], cwd=scope)
    print('[7/10] Running selected Operational Data tests by capability')
    _run_tests(capabilities, scope)
    print('[8/10] Validating productive/commented semantic mirrors')
    _validate_mirrors(capabilities, scope, repository)
    print('[9/10] Validating public imports')
    _validate_imports(capabilities, scope)
    print('[10/10] Building selected Operational Data wheels')
    _build_wheels(capabilities, scope)
    print('Atlanticus Operational Data validated:', ', '.join(item.key for item in capabilities))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
