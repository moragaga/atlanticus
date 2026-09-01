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

# El gate conserva un baseline general y sólo declara excepciones de versión explícitas.
EXPECTED_PYTHON_VERSION = '3.14.2'
DEFAULT_PROJECT_VERSION = '1.0.0'
PROJECT_VERSION_OVERRIDES = {
    'ada-kpi-runtime-process': '1.0.1',
}
LEGACY_PATTERN = re.compile(r'\b(?:KpiSource|KpiPartition|SourceRequirement)\b|ada\.data\.')
PROCESS_FORBIDDEN_IMPORTS = ('ada.web', 'atlanticus.data_producers')


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
    'kpi-runtime': Capability(
        'kpi-runtime',
        'ada-kpi-runtime-process',
        'ada.processes.kpi_runtime',
        'processes/kpi-runtime',
        (
            'ada-kpis-core==1.0.0',
            'ada-kpis-evaluation==1.0.0',
            'ada-kpis-persistence==1.0.0',
            'atlanticus-configuration==1.0.0',
            'atlanticus-datasets-parquet==1.0.0',
            'atlanticus-datasets-runtime==1.0.0',
            'atlanticus-job-runtime==1.0.0',
            'atlanticus-key-vault==1.0.0',
            'atlanticus-kernel==1.0.0',
            'atlanticus-observability-azure==1.0.0',
            'atlanticus-operational-data-core==1.0.0',
            'atlanticus-operational-data-planner==1.0.0',
            'atlanticus-operational-data-sources==1.0.0',
            'atlanticus-state==1.0.0',
        ),
    ),
    'kpi-delivery': Capability(
        'kpi-delivery',
        'ada-kpis-delivery',
        'ada.kpis.delivery',
        'kpis/delivery',
        (),
    ),
    'kpi-delivery-runtime': Capability(
        'kpi-delivery-runtime',
        'ada-kpi-delivery-process',
        'ada.processes.kpi_delivery',
        'processes/kpi-delivery',
        (
            'ada-kpis-core==1.0.0',
            'ada-kpis-delivery==1.0.0',
            'ada-kpis-persistence==1.0.0',
            'atlanticus-configuration==1.0.0',
            'atlanticus-cosmos==1.0.0',
            'atlanticus-job-runtime==1.0.0',
            'atlanticus-key-vault==1.0.0',
            'atlanticus-kernel==1.0.0',
            'atlanticus-observability-azure==1.0.0',
            'atlanticus-state==1.0.0',
        ),
    ),
    'kpi-history': Capability(
        'kpi-history',
        'ada-kpis-history',
        'ada.kpis.history',
        'kpis/history',
        ('atlanticus-datasets==1.0.0', 'pyarrow==25.0.0'),
    ),
    'kpi-historian-runtime': Capability(
        'kpi-historian-runtime',
        'ada-kpi-historian-process',
        'ada.processes.kpi_historian',
        'processes/kpi-historian',
        (
            'ada-kpis-core==1.0.0',
            'ada-kpis-history==1.0.0',
            'ada-kpis-persistence==1.0.0',
            'atlanticus-configuration==1.0.0',
            'atlanticus-datasets-parquet==1.0.0',
            'atlanticus-datasets-runtime==1.0.0',
            'atlanticus-job-runtime==1.0.0',
            'atlanticus-key-vault==1.0.0',
            'atlanticus-kernel==1.0.0',
            'atlanticus-observability-azure==1.0.0',
            'atlanticus-state==1.0.0',
            'pyarrow==25.0.0',
        ),
    ),
    'kpi-timeseries-delivery-runtime': Capability(
        'kpi-timeseries-delivery-runtime',
        'ada-kpi-timeseries-delivery-process',
        'ada.processes.kpi_timeseries_delivery',
        'processes/kpi-timeseries-delivery',
        (
            'ada-kpis-core==1.0.0',
            'ada-kpis-delivery==1.0.0',
            'ada-kpis-history==1.0.0',
            'atlanticus-configuration==1.0.0',
            'atlanticus-cosmos==1.0.0',
            'atlanticus-datasets-parquet==1.0.0',
            'atlanticus-datasets-runtime==1.0.0',
            'atlanticus-job-runtime==1.0.0',
            'atlanticus-key-vault==1.0.0',
            'atlanticus-kernel==1.0.0',
            'atlanticus-observability-azure==1.0.0',
            'atlanticus-state==1.0.0',
        ),
    ),
}

EXPECTED_MEMBERS = [
    'kpis/core',
    'kpis/evaluation',
    'kpis/persistence',
    'processes/kpi-runtime',
    'kpis/delivery',
    'processes/kpi-delivery',
    'kpis/history',
    'processes/kpi-historian',
    'processes/kpi-timeseries-delivery',
]

EXPECTED_SOURCES = {
    'ada-kpi-runtime-process': {'workspace': True},
    'ada-kpi-delivery-process': {'workspace': True},
    'ada-kpi-historian-process': {'workspace': True},
    'ada-kpis-core': {'workspace': True},
    'ada-kpis-evaluation': {'workspace': True},
    'ada-kpis-persistence': {'workspace': True},
    'ada-kpis-delivery': {'workspace': True},
    'ada-kpis-history': {'workspace': True},
    'atlanticus-configuration': {'path': '../../../backend/configuration', 'editable': True},
    'atlanticus-cosmos': {'path': '../../../connectivity/cosmos', 'editable': True},
    'atlanticus-datasets': {'path': '../../../backend/datasets', 'editable': True},
    'atlanticus-datasets-parquet': {
        'path': '../../../backend/datasets-parquet',
        'editable': True,
    },
    'atlanticus-datasets-runtime': {
        'path': '../../../backend/datasets-runtime',
        'editable': True,
    },
    'atlanticus-job-runtime': {'path': '../../../backend/runtime', 'editable': True},
    'atlanticus-json': {'path': '../../../backend/json', 'editable': True},
    'atlanticus-kernel': {'path': '../../../backend/kernel', 'editable': True},
    'atlanticus-key-vault': {'path': '../../../connectivity/key-vault', 'editable': True},
    'atlanticus-observability': {'path': '../../../backend/observability', 'editable': True},
    'atlanticus-observability-azure': {
        'path': '../../../backend/observability-azure',
        'editable': True,
    },
    'atlanticus-operational-data-calendar': {
        'path': '../../operational-data/calendar',
        'editable': True,
    },
    'atlanticus-operational-data-core': {
        'path': '../../operational-data/core',
        'editable': True,
    },
    'atlanticus-operational-data-planner': {
        'path': '../../operational-data/planner',
        'editable': True,
    },
    'atlanticus-operational-data-sources': {
        'path': '../../operational-data/sources',
        'editable': True,
    },
    'atlanticus-state': {'path': '../../../backend/state', 'editable': True},
    'ada-kpi-timeseries-delivery-process': {'workspace': True},
}

LOCAL_BASELINES = {
    'atlanticus-configuration': 'backend/configuration',
    'atlanticus-cosmos': 'connectivity/cosmos',
    'atlanticus-datasets': 'backend/datasets',
    'atlanticus-datasets-parquet': 'backend/datasets-parquet',
    'atlanticus-datasets-runtime': 'backend/datasets-runtime',
    'atlanticus-job-runtime': 'backend/runtime',
    'atlanticus-json': 'backend/json',
    'atlanticus-kernel': 'backend/kernel',
    'atlanticus-key-vault': 'connectivity/key-vault',
    'atlanticus-observability': 'backend/observability',
    'atlanticus-observability-azure': 'backend/observability-azure',
    'atlanticus-operational-data-calendar': 'scopes/operational-data/calendar',
    'atlanticus-operational-data-core': 'scopes/operational-data/core',
    'atlanticus-operational-data-planner': 'scopes/operational-data/planner',
    'atlanticus-operational-data-sources': 'scopes/operational-data/sources',
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


# Una única autoridad de versión alimenta tanto identity validation como wheel qualification.
def _expected_project_version(distribution: str) -> str:
    return PROJECT_VERSION_OVERRIDES.get(distribution, DEFAULT_PROJECT_VERSION)


# El diagnóstico muestra la identidad esperada y encontrada para detectar contratos antiguos.
def _validate_project(path: Path, distribution: str) -> None:
    project = _project(path / 'pyproject.toml')
    expected_version = _expected_project_version(distribution)
    actual_name = project.get('name')
    actual_version = project.get('version')
    if actual_name != distribution or actual_version != expected_version:
        raise SystemExit(
            f'Unexpected project identity at {path}: '
            f'expected {distribution}=={expected_version}, '
            f'found {actual_name}=={actual_version}'
        )


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
    if not isinstance(workspace, dict) or workspace.get('members') != EXPECTED_MEMBERS:
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
    _validate_runtime_process_contract(scope)
    _validate_delivery_process_contract(scope)
    _validate_historian_process_contract(scope)
    _validate_timeseries_delivery_process_contract(scope)


def _validate_runtime_process_contract(scope: Path) -> None:
    root = scope / 'processes/kpi-runtime'
    document = _read(root / 'pyproject.toml')
    project = document.get('project')
    tool = document.get('tool')
    if not isinstance(project, dict) or not isinstance(tool, dict):
        raise SystemExit('KPI Runtime project metadata is incomplete')
    if project.get('scripts') != {'ada-kpi-runtime': 'ada.processes.kpi_runtime.bootstrap:main'}:
        raise SystemExit('KPI Runtime entrypoint is not canonical')
    atlanticus = tool.get('atlanticus')
    container = atlanticus.get('container') if isinstance(atlanticus, dict) else None
    if container != {'command': 'ada-kpi-runtime', 'system-profile': 'base'}:
        raise SystemExit('KPI Runtime container contract is not canonical')
    for name in ('.python-version', '.env.detail', 'config.detail.json', 'secrets.detail.json'):
        if not (root / name).is_file():
            raise SystemExit(f'KPI Runtime process contract file is missing: {name}')


def _validate_delivery_process_contract(scope: Path) -> None:
    root = scope / 'processes/kpi-delivery'
    document = _read(root / 'pyproject.toml')
    project = document.get('project')
    tool = document.get('tool')
    if not isinstance(project, dict) or not isinstance(tool, dict):
        raise SystemExit('KPI Delivery project metadata is incomplete')
    expected_script = {'ada-kpi-delivery': 'ada.processes.kpi_delivery.bootstrap:main'}
    if project.get('scripts') != expected_script:
        raise SystemExit('KPI Delivery entrypoint is not canonical')
    atlanticus = tool.get('atlanticus')
    container = atlanticus.get('container') if isinstance(atlanticus, dict) else None
    if container != {'command': 'ada-kpi-delivery', 'system-profile': 'base'}:
        raise SystemExit('KPI Delivery container contract is not canonical')
    for name in ('.python-version', '.env.detail', 'config.detail.json', 'secrets.detail.json'):
        if not (root / name).is_file():
            raise SystemExit(f'KPI Delivery process contract file is missing: {name}')


def _validate_historian_process_contract(scope: Path) -> None:
    root = scope / 'processes/kpi-historian'
    document = _read(root / 'pyproject.toml')
    project = document.get('project')
    tool = document.get('tool')
    if not isinstance(project, dict) or not isinstance(tool, dict):
        raise SystemExit('KPI Historian project metadata is incomplete')
    expected_script = {'ada-kpi-historian': 'ada.processes.kpi_historian.bootstrap:main'}
    if project.get('scripts') != expected_script:
        raise SystemExit('KPI Historian entrypoint is not canonical')
    atlanticus = tool.get('atlanticus')
    container = atlanticus.get('container') if isinstance(atlanticus, dict) else None
    if container != {'command': 'ada-kpi-historian', 'system-profile': 'base'}:
        raise SystemExit('KPI Historian container contract is not canonical')
    for name in ('.python-version', '.env.detail', 'config.detail.json', 'secrets.detail.json'):
        if not (root / name).is_file():
            raise SystemExit(f'KPI Historian process contract file is missing: {name}')


def _validate_timeseries_delivery_process_contract(scope: Path) -> None:
    root = scope / 'processes/kpi-timeseries-delivery'
    document = _read(root / 'pyproject.toml')
    project = document.get('project')
    tool = document.get('tool')
    if not isinstance(project, dict) or not isinstance(tool, dict):
        raise SystemExit('KPI Timeseries Delivery project metadata is incomplete')
    expected_script = {
        'ada-kpi-timeseries-delivery': 'ada.processes.kpi_timeseries_delivery.bootstrap:main'
    }
    if project.get('scripts') != expected_script:
        raise SystemExit('KPI Timeseries Delivery entrypoint is not canonical')
    atlanticus = tool.get('atlanticus')
    container = atlanticus.get('container') if isinstance(atlanticus, dict) else None
    if container != {
        'command': 'ada-kpi-timeseries-delivery',
        'system-profile': 'base',
    }:
        raise SystemExit('KPI Timeseries Delivery container contract is not canonical')
    for name in ('.python-version', '.env.detail', 'config.detail.json', 'secrets.detail.json'):
        if not (root / name).is_file():
            raise SystemExit(f'KPI Timeseries Delivery process contract file is missing: {name}')


def _validate_ownership(repository: Path, scope: Path) -> None:
    if (repository / 'scopes/ada/kpis').exists():
        raise SystemExit(
            'Legacy scopes/ada/kpis authority must not coexist with ADA backend KPI domain'
        )
    if (repository / 'scopes/ada/processes/kpis').exists():
        raise SystemExit(
            'Legacy scopes/ada/processes/kpis authority must not coexist with KPI Runtime'
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
            if capability.key in {
                'kpi-runtime',
                'kpi-delivery-runtime',
                'kpi-historian-runtime',
                'kpi-timeseries-delivery-runtime',
            } and any(token in text for token in PROCESS_FORBIDDEN_IMPORTS):
                raise SystemExit(f'Forbidden KPI Runtime dependency found in {path}')


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


# La búsqueda del wheel usa la misma versión esperada que la validación del proyecto.
def _build_wheels(selected: tuple[Capability, ...], scope: Path) -> None:
    dist = scope / 'dist'
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir(parents=True)
    for capability in selected:
        _run(['uv', 'build', capability.root, '--wheel', '--out-dir', str(dist)], cwd=scope)
        expected_version = _expected_project_version(capability.distribution)
        prefix = capability.distribution.replace('-', '_') + f'-{expected_version}-'
        wheels = tuple(path for path in dist.glob('*.whl') if path.name.startswith(prefix))
        if len(wheels) != 1:
            raise SystemExit(
                f'Expected exactly one wheel for {capability.distribution}=={expected_version}'
            )
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
