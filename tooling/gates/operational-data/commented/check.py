from __future__ import annotations

import argparse
import ast
import os
import platform
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile

# Mantiene el baseline vigente mientras la migración global de Python siga fuera de este incremento.
EXPECTED_PYTHON_VERSION = '3.14.2'
BOOTSTRAP_ENVIRONMENT_VARIABLE = 'ATLANTICUS_OPERATIONAL_DATA_GATE_BOOTSTRAPPED'
DEPENDENCY_PATTERN = re.compile(r'^([A-Za-z0-9_.-]+)==(.+)$')


# Describe cada capability validable sin convertir el gate en dueño de su versión.
@dataclass(frozen=True, slots=True)
class OperationalDataCapability:
    key: str
    distribution: str
    import_name: str
    project_root: str
    source_root: str
    commented_root: str


# Inventario lógico de las 16 capabilities que componen el workspace Operational Data.
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
    'producer-core': OperationalDataCapability(
        'producer-core',
        'atlanticus-data-producers-core',
        'atlanticus.data_producers.core',
        'producers/core',
        'producers/core/src',
        'producers/core/commented',
    ),
    'producer-sql': OperationalDataCapability(
        'producer-sql',
        'atlanticus-data-producers-sql',
        'atlanticus.data_producers.sql',
        'producers/sql',
        'producers/sql/src',
        'producers/sql/commented',
    ),
    'producer-pi': OperationalDataCapability(
        'producer-pi',
        'atlanticus-data-producers-pi',
        'atlanticus.data_producers.pi',
        'producers/pi',
        'producers/pi/src',
        'producers/pi/commented',
    ),
    'producer-notpii': OperationalDataCapability(
        'producer-notpii',
        'atlanticus-data-producers-notpii',
        'atlanticus.data_producers.notpii',
        'producers/notpii',
        'producers/notpii/src',
        'producers/notpii/commented',
    ),
    'producer-fabrica': OperationalDataCapability(
        'producer-fabrica',
        'atlanticus-data-producers-fabrica',
        'atlanticus.data_producers.fabrica',
        'producers/fabrica',
        'producers/fabrica/src',
        'producers/fabrica/commented',
    ),
    'producer-remanentes': OperationalDataCapability(
        'producer-remanentes',
        'atlanticus-data-producers-remanentes',
        'atlanticus.data_producers.remanentes',
        'producers/remanentes',
        'producers/remanentes/src',
        'producers/remanentes/commented',
    ),
    'process-pi': OperationalDataCapability(
        'process-pi',
        'atlanticus-operational-data-pi-process',
        'atlanticus.operational_data.processes.pi',
        'processes/pi',
        'processes/pi/src',
        'processes/pi/commented',
    ),
    'process-notpii': OperationalDataCapability(
        'process-notpii',
        'atlanticus-operational-data-notpii-process',
        'atlanticus.operational_data.processes.notpii',
        'processes/notpii',
        'processes/notpii/src',
        'processes/notpii/commented',
    ),
    'process-dispatch': OperationalDataCapability(
        'process-dispatch',
        'atlanticus-operational-data-dispatch-process',
        'atlanticus.operational_data.processes.dispatch',
        'processes/dispatch',
        'processes/dispatch/src',
        'processes/dispatch/commented',
    ),
    'process-blockgrade': OperationalDataCapability(
        'process-blockgrade',
        'atlanticus-operational-data-blockgrade-process',
        'atlanticus.operational_data.processes.blockgrade',
        'processes/blockgrade',
        'processes/blockgrade/src',
        'processes/blockgrade/commented',
    ),
    'process-fabrica': OperationalDataCapability(
        'process-fabrica',
        'atlanticus-operational-data-fabrica-process',
        'atlanticus.operational_data.processes.fabrica',
        'processes/fabrica',
        'processes/fabrica/src',
        'processes/fabrica/commented',
    ),
    'process-remanentes': OperationalDataCapability(
        'process-remanentes',
        'atlanticus-operational-data-remanentes-process',
        'atlanticus.operational_data.processes.remanentes',
        'processes/remanentes',
        'processes/remanentes/src',
        'processes/remanentes/commented',
    ),
}

# El orden del workspace es parte del contrato de composición actual.
EXPECTED_WORKSPACE_MEMBERS = [
    'core',
    'planner',
    'calendar',
    'sources',
    'producers/core',
    'producers/sql',
    'producers/pi',
    'producers/notpii',
    'producers/fabrica',
    'producers/remanentes',
    'processes/pi',
    'processes/notpii',
    'processes/dispatch',
    'processes/blockgrade',
    'processes/fabrica',
    'processes/remanentes',
]

# Las fuentes locales pertenecen al workspace raíz; los miembros no duplican tool.uv.sources.
EXPECTED_WORKSPACE_SOURCES = {
    'atlanticus-operational-data-core': {'workspace': True},
    'atlanticus-operational-data-planner': {'workspace': True},
    'atlanticus-operational-data-calendar': {'workspace': True},
    'atlanticus-operational-data-sources': {'workspace': True},
    'atlanticus-data-producers-core': {'workspace': True},
    'atlanticus-data-producers-sql': {'workspace': True},
    'atlanticus-data-producers-pi': {'workspace': True},
    'atlanticus-data-producers-notpii': {'workspace': True},
    'atlanticus-data-producers-fabrica': {'workspace': True},
    'atlanticus-data-producers-remanentes': {'workspace': True},
    'atlanticus-operational-data-pi-process': {'workspace': True},
    'atlanticus-operational-data-notpii-process': {'workspace': True},
    'atlanticus-operational-data-dispatch-process': {'workspace': True},
    'atlanticus-operational-data-blockgrade-process': {'workspace': True},
    'atlanticus-operational-data-fabrica-process': {'workspace': True},
    'atlanticus-operational-data-remanentes-process': {'workspace': True},
    'atlanticus-configuration': {'path': '../../backend/configuration', 'editable': True},
    'atlanticus-datasets': {'path': '../../backend/datasets', 'editable': True},
    'atlanticus-datasets-parquet': {'path': '../../backend/datasets-parquet', 'editable': True},
    'atlanticus-datasets-runtime': {'path': '../../backend/datasets-runtime', 'editable': True},
    'atlanticus-job-runtime': {'path': '../../backend/runtime', 'editable': True},
    'atlanticus-kernel': {'path': '../../backend/kernel', 'editable': True},
    'atlanticus-observability': {'path': '../../backend/observability', 'editable': True},
    'atlanticus-observability-azure': {
        'path': '../../backend/observability-azure',
        'editable': True,
    },
    'atlanticus-state': {'path': '../../backend/state', 'editable': True},
    'atlanticus-http': {'path': '../../connectivity/http-client', 'editable': True},
    'atlanticus-key-vault': {'path': '../../connectivity/key-vault', 'editable': True},
    'atlanticus-service-bus': {'path': '../../connectivity/service-bus', 'editable': True},
    'atlanticus-sql': {'path': '../../connectivity/sql', 'editable': True},
    'atlanticus-storage': {'path': '../../connectivity/storage', 'editable': True},
    'atlanticus-pi-contracts': {'path': '../../integrations/pi/contracts', 'editable': True},
    'atlanticus-pi-web-api': {'path': '../../integrations/pi/web-api', 'editable': True},
}

# Se congela la topología de dependencias, pero las versiones locales se correlacionan con cada pyproject.
EXPECTED_DEPENDENCY_NAMES = {
    'core': (),
    'planner': ('atlanticus-operational-data-core',),
    'calendar': (),
    'sources': (
        'atlanticus-operational-data-calendar',
        'atlanticus-operational-data-core',
        'atlanticus-operational-data-planner',
        'atlanticus-datasets',
        'pandas',
        'pyarrow',
    ),
    'producer-core': (),
    'producer-sql': (
        'atlanticus-data-producers-core',
        'atlanticus-datasets',
        'atlanticus-datasets-parquet',
        'atlanticus-datasets-runtime',
        'atlanticus-job-runtime',
        'atlanticus-sql',
        'atlanticus-state',
        'pyarrow',
    ),
    'producer-pi': (
        'atlanticus-datasets',
        'atlanticus-datasets-parquet',
        'atlanticus-datasets-runtime',
        'atlanticus-job-runtime',
        'atlanticus-observability',
        'atlanticus-pi-contracts',
        'atlanticus-pi-web-api',
        'atlanticus-state',
        'pyarrow',
    ),
    'producer-notpii': (
        'atlanticus-datasets',
        'atlanticus-datasets-parquet',
        'atlanticus-datasets-runtime',
        'atlanticus-job-runtime',
        'atlanticus-pi-contracts',
        'atlanticus-service-bus',
        'atlanticus-state',
        'atlanticus-storage',
        'pandas',
        'pyarrow',
    ),
    'producer-fabrica': (
        'atlanticus-datasets',
        'atlanticus-datasets-parquet',
        'atlanticus-datasets-runtime',
        'atlanticus-job-runtime',
        'atlanticus-observability',
        'atlanticus-state',
        'atlanticus-storage',
        'pandas',
        'pyarrow',
    ),
    'producer-remanentes': (
        'atlanticus-datasets',
        'atlanticus-datasets-parquet',
        'atlanticus-datasets-runtime',
        'atlanticus-job-runtime',
        'atlanticus-observability',
        'atlanticus-state',
        'atlanticus-storage',
        'pandas',
        'pyarrow',
    ),
    'process-pi': (
        'atlanticus-configuration',
        'atlanticus-data-producers-pi',
        'atlanticus-http',
        'atlanticus-job-runtime',
        'atlanticus-kernel',
        'atlanticus-key-vault',
        'atlanticus-observability-azure',
        'atlanticus-pi-contracts',
        'atlanticus-pi-web-api',
    ),
    'process-notpii': (
        'atlanticus-configuration',
        'atlanticus-data-producers-notpii',
        'atlanticus-job-runtime',
        'atlanticus-kernel',
        'atlanticus-key-vault',
        'atlanticus-observability-azure',
        'atlanticus-pi-contracts',
        'atlanticus-service-bus',
    ),
    'process-dispatch': (
        'atlanticus-operational-data-calendar',
        'atlanticus-configuration',
        'atlanticus-data-producers-core',
        'atlanticus-data-producers-sql',
        'atlanticus-job-runtime',
        'atlanticus-kernel',
        'atlanticus-key-vault',
        'atlanticus-observability-azure',
        'atlanticus-sql',
    ),
    'process-blockgrade': (
        'atlanticus-operational-data-calendar',
        'atlanticus-configuration',
        'atlanticus-data-producers-core',
        'atlanticus-data-producers-sql',
        'atlanticus-job-runtime',
        'atlanticus-kernel',
        'atlanticus-key-vault',
        'atlanticus-observability-azure',
        'atlanticus-sql',
    ),
    'process-fabrica': (
        'atlanticus-configuration',
        'atlanticus-data-producers-fabrica',
        'atlanticus-job-runtime',
        'atlanticus-kernel',
        'atlanticus-key-vault',
        'atlanticus-observability-azure',
        'atlanticus-storage',
    ),
    'process-remanentes': (
        'atlanticus-configuration',
        'atlanticus-data-producers-remanentes',
        'atlanticus-job-runtime',
        'atlanticus-kernel',
        'atlanticus-key-vault',
        'atlanticus-observability-azure',
        'atlanticus-storage',
    ),
}

# Paquetes Atlanticus externos al scope que participan del grafo local de desarrollo.
LOCAL_BASELINES = {
    'atlanticus-configuration': 'backend/configuration',
    'atlanticus-datasets': 'backend/datasets',
    'atlanticus-datasets-parquet': 'backend/datasets-parquet',
    'atlanticus-datasets-runtime': 'backend/datasets-runtime',
    'atlanticus-job-runtime': 'backend/runtime',
    'atlanticus-kernel': 'backend/kernel',
    'atlanticus-observability': 'backend/observability',
    'atlanticus-observability-azure': 'backend/observability-azure',
    'atlanticus-state': 'backend/state',
    'atlanticus-http': 'connectivity/http-client',
    'atlanticus-key-vault': 'connectivity/key-vault',
    'atlanticus-service-bus': 'connectivity/service-bus',
    'atlanticus-sql': 'connectivity/sql',
    'atlanticus-storage': 'connectivity/storage',
    'atlanticus-pi-contracts': 'integrations/pi/contracts',
    'atlanticus-pi-web-api': 'integrations/pi/web-api',
}

# Contrato de entrypoint y perfil de sistema de los seis procesos desplegables.
PROCESS_CONTRACTS = {
    'process-pi': ('operational-data-pi', 'base'),
    'process-notpii': ('operational-data-notpii', 'base'),
    'process-dispatch': ('operational-data-dispatch', 'sqlserver'),
    'process-blockgrade': ('operational-data-blockgrade', 'sqlserver'),
    'process-fabrica': ('operational-data-fabrica', 'base'),
    'process-remanentes': ('operational-data-remanentes', 'base'),
}

# Tokens que no pueden reaparecer porque moverían ownership nuevamente hacia ADA.
LEGACY_TOKENS = (
    'ada.data.',
    'ada.operational_calendar',
    'ada-operational-data-',
    'ada-operational-calendar',
    'ADA_OPERATIONAL_CALENDARS',
    'ada.processes.pi_web_api',
    'ada.processes.notpii',
    'ada.processes.dispatch',
    'ada.processes.blockgrade',
    'ada.processes.fabrica',
    'ada.processes.remanentes',
)
LEGACY_PATH_TOKENS = ('src/ada/processes/', 'commented/ada/processes/')
# Rutas históricas incompatibles con la ownership actual de Operational Data.
RETIRED_PROCESS_PATHS = (
    'scopes/ada/processes/pi-web-api',
    'scopes/ada/processes/notpii',
    'scopes/ada/processes/dispatch',
    'scopes/ada/processes/blockgrade',
    'scopes/ada/processes/fabrica',
    'scopes/ada/processes/remanentes',
)


# Resuelve la raíz sin depender de una profundidad fija del archivo.
def _repository_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / 'scopes/operational-data/pyproject.toml').is_file():
            return candidate
    raise SystemExit('Repository root could not be resolved')


def _scope_root() -> Path:
    return _repository_root() / 'scopes/operational-data'


def _run(command: list[str], *, cwd: Path, environment: dict[str, str] | None = None) -> None:
    print('> ' + ' '.join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=environment, check=True)


# Conserva selección granular, ejecución total, listado y limpieza explícita.
def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Validate Atlanticus Operational Data capabilities.'
    )
    parser.add_argument('capabilities', nargs='*')
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--clean', action='store_true')
    return parser


def _resolve_capabilities(arguments: argparse.Namespace) -> tuple[OperationalDataCapability, ...]:
    if arguments.list:
        print('\n'.join(CAPABILITIES))
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
    return tuple(dict.fromkeys(CAPABILITIES[key] for key in requested))


def _read_toml(path: Path) -> dict[str, object]:
    with path.open('rb') as stream:
        return tomllib.load(stream)


def _project(path: Path) -> dict[str, object]:
    project = _read_toml(path).get('project')
    if not isinstance(project, dict):
        raise SystemExit(f'Missing [project] table: {path}')
    return project


# Lee identidad y versión desde el pyproject dueño del paquete.
def _project_version(path: Path, distribution: str) -> str:
    project = _project(path / 'pyproject.toml')
    if project.get('name') != distribution:
        raise SystemExit(
            f'Unexpected distribution at {path}: expected {distribution}, '
            f'found {project.get("name")!r}'
        )
    version = project.get('version')
    if not isinstance(version, str) or not version.strip():
        raise SystemExit(f'Missing project version for {distribution}: {path}')
    return version


# Limpia únicamente estado regenerable del workspace cuando el usuario solicita --clean.
def _cleanup(scope: Path) -> None:
    for generated in (scope / '.venv', scope / 'dist'):
        if generated.is_dir():
            shutil.rmtree(generated)
        elif generated.exists():
            generated.unlink()
    for capability in CAPABILITIES.values():
        project_root = scope / capability.project_root
        for relative in ('build', '.pytest_cache', '.ruff_cache'):
            generated = project_root / relative
            if generated.is_dir():
                shutil.rmtree(generated)
            elif generated.exists():
                generated.unlink()
        for egg_info in project_root.rglob('*.egg-info'):
            if egg_info.is_dir():
                shutil.rmtree(egg_info)
            elif egg_info.exists():
                egg_info.unlink()


# Valida lock, sincroniza el workspace non-editable y reejecuta bajo Python exacto.
def _bootstrap(raw_argv: list[str], *, clean: bool) -> None:
    if os.environ.get(BOOTSTRAP_ENVIRONMENT_VARIABLE) == '1':
        return
    scope = _scope_root()
    if not (scope / 'uv.lock').is_file():
        raise SystemExit(
            'scopes/operational-data/uv.lock is missing. '
            'Run uv lock from scopes/operational-data first.'
        )
    if clean:
        _cleanup(scope)
    print('[bootstrap] Validating locked Operational Data dependency graph', flush=True)
    _run(['uv', 'lock', '--check'], cwd=scope)
    reinstall = [
        *LOCAL_BASELINES,
        *(capability.distribution for capability in CAPABILITIES.values()),
    ]
    command = [
        'uv',
        'sync',
        '--python',
        EXPECTED_PYTHON_VERSION,
        '--no-python-downloads',
        '--frozen',
        '--all-packages',
        '--group',
        'dev',
        '--no-editable',
    ]
    for distribution in reinstall:
        command.extend(['--reinstall-package', distribution])
    print('[bootstrap] Synchronizing frozen Operational Data workspace', flush=True)
    _run(command, cwd=scope)
    environment = os.environ.copy()
    environment[BOOTSTRAP_ENVIRONMENT_VARIABLE] = '1'
    completed = subprocess.run(
        [
            'uv',
            'run',
            '--python',
            EXPECTED_PYTHON_VERSION,
            '--no-python-downloads',
            '--no-sync',
            'python',
            str(Path(__file__).resolve()),
            *raw_argv,
        ],
        cwd=scope,
        env=environment,
        check=False,
    )
    raise SystemExit(completed.returncode)


def _validate_python() -> None:
    found = platform.python_version()
    if found != EXPECTED_PYTHON_VERSION:
        raise SystemExit(f'Expected Python {EXPECTED_PYTHON_VERSION}, found {found}')


# Congela composición y ownership del workspace sin congelar una versión global de release.
def _validate_workspace(scope: Path, repository: Path) -> None:
    document = _read_toml(scope / 'pyproject.toml')
    project = document.get('project')
    if (
        not isinstance(project, dict)
        or project.get('name') != 'atlanticus-operational-data-workspace'
    ):
        raise SystemExit('Unexpected Operational Data workspace identity')
    workspace_version = project.get('version')
    if not isinstance(workspace_version, str) or not workspace_version.strip():
        raise SystemExit('Missing Operational Data workspace version')
    if project.get('dependencies') != []:
        raise SystemExit(
            'Operational Data workspace must not pin member versions as root dependencies'
        )
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
        capability_uv = capability_tool.get('uv')
        if isinstance(capability_uv, dict) and 'sources' in capability_uv:
            raise SystemExit(
                f'{capability.distribution} must inherit local sources from the scope workspace'
            )
    uv = tool.get('uv')
    if not isinstance(uv, dict):
        raise SystemExit('Missing [tool.uv] configuration in Operational Data workspace')
    workspace = uv.get('workspace')
    if not isinstance(workspace, dict) or workspace.get('members') != EXPECTED_WORKSPACE_MEMBERS:
        raise SystemExit('Operational Data workspace members are not canonical')
    sources = uv.get('sources')
    if sources != EXPECTED_WORKSPACE_SOURCES:
        raise SystemExit('Operational Data workspace source registry is not canonical')
    for distribution, expected in EXPECTED_WORKSPACE_SOURCES.items():
        if 'path' not in expected:
            continue
        target = (scope / str(expected['path'])).resolve()
        try:
            target.relative_to(repository.resolve())
        except ValueError as error:
            raise SystemExit(f'{distribution} UV source escapes repository') from error
        if not (target / 'pyproject.toml').is_file():
            raise SystemExit(f'{distribution} source target is missing: {target}')


# Construye el registro de proyectos locales a partir de capabilities y baselines existentes.
def _local_project_roots(scope: Path, repository: Path) -> dict[str, Path]:
    roots = {
        capability.distribution: scope / capability.project_root
        for capability in CAPABILITIES.values()
    }
    roots.update(
        {distribution: repository / relative for distribution, relative in LOCAL_BASELINES.items()}
    )
    return roots


# Requiere pins exactos para correlacionar cada dependencia local con su dueño.
def _parse_dependencies(project_root: Path) -> tuple[tuple[str, str], ...]:
    dependencies = _project(project_root / 'pyproject.toml').get('dependencies')
    if not isinstance(dependencies, list) or not all(
        isinstance(value, str) for value in dependencies
    ):
        raise SystemExit(f'Invalid dependency list: {project_root}')
    parsed: list[tuple[str, str]] = []
    for dependency in dependencies:
        match = DEPENDENCY_PATTERN.fullmatch(dependency)
        if match is None:
            raise SystemExit(
                f'Operational Data dependencies must use exact pins: {project_root}: {dependency}'
            )
        parsed.append((match.group(1), match.group(2)))
    return tuple(parsed)


# Verifica topología declarada y que cada pin local coincida con la versión real del paquete.
def _validate_dependency_correlation(scope: Path, repository: Path) -> None:
    local_roots = _local_project_roots(scope, repository)
    local_versions = {
        distribution: _project_version(project_root, distribution)
        for distribution, project_root in local_roots.items()
    }
    for capability in CAPABILITIES.values():
        project_root = scope / capability.project_root
        _project_version(project_root, capability.distribution)
        dependencies = _parse_dependencies(project_root)
        dependency_names = tuple(name for name, _ in dependencies)
        if dependency_names != EXPECTED_DEPENDENCY_NAMES[capability.key]:
            raise SystemExit(
                f'Unexpected dependency names for {capability.distribution}: {dependency_names!r}'
            )
        for name, pinned_version in dependencies:
            expected_version = local_versions.get(name)
            if expected_version is not None and pinned_version != expected_version:
                raise SystemExit(
                    f'Local dependency version mismatch for {capability.distribution}: '
                    f'{name}=={pinned_version}, expected {name}=={expected_version}'
                )


# Impide coexistencia de authorities antiguas y nuevas.
def _validate_retired_paths(repository: Path) -> None:
    remaining = [relative for relative in RETIRED_PROCESS_PATHS if (repository / relative).exists()]
    if remaining:
        raise SystemExit(
            'Retired Operational Data authority is still present: ' + ', '.join(remaining)
        )


# Evita que Operational Data vuelva a depender de namespaces históricos de ADA.
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
            normalized = ''.join(character for character in text if character not in ' \t\r\n\'"')
            for token in LEGACY_PATH_TOKENS:
                if token in normalized:
                    raise SystemExit(f'Legacy ADA ownership path {token!r} found in {path}')


# Cada composition root puede usar su propio namespace pero no importar otro process.
def _validate_process_isolation(scope: Path) -> None:
    prefix = 'atlanticus.operational_data.processes.'
    for key in PROCESS_CONTRACTS:
        capability = CAPABILITIES[key]
        source = scope / capability.source_root
        for path in source.rglob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
            imported: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    imported.append(node.module)
                elif isinstance(node, ast.Import):
                    imported.extend(alias.name for alias in node.names)
            for module in imported:
                if not module.startswith(prefix):
                    continue
                if module == capability.import_name or module.startswith(
                    capability.import_name + '.'
                ):
                    continue
                raise SystemExit(f'Process-to-process import is forbidden: {path} -> {module}')


# Centraliza los invariantes estructurales comunes que antes se repetían en tests por proceso.
def _validate_process_contracts(scope: Path) -> None:
    for key, (command, system_profile) in PROCESS_CONTRACTS.items():
        capability = CAPABILITIES[key]
        root = scope / capability.project_root
        for name in ('.python-version', '.env.detail', 'config.detail.json', 'secrets.detail.json'):
            if not (root / name).is_file():
                raise SystemExit(
                    f'{capability.distribution} process contract file is missing: {name}'
                )
        python_version = (root / '.python-version').read_text(encoding='utf-8').strip()
        if python_version != EXPECTED_PYTHON_VERSION:
            raise SystemExit(
                f'{capability.distribution} .python-version must be '
                f'{EXPECTED_PYTHON_VERSION}, found {python_version}'
            )
        for retired in ('.env', 'uv.lock', 'FIRST_STEP.txt'):
            if (root / retired).exists():
                raise SystemExit(
                    f'{capability.distribution} source process contains retired local state: {retired}'
                )
        document = _read_toml(root / 'pyproject.toml')
        project = document.get('project')
        tool = document.get('tool')
        if not isinstance(project, dict) or not isinstance(tool, dict):
            raise SystemExit(f'{capability.distribution} process project metadata is incomplete')
        if project.get('scripts') != {command: f'{capability.import_name}.bootstrap:main'}:
            raise SystemExit(f'{capability.distribution} process entrypoint is not canonical')
        atlanticus = tool.get('atlanticus')
        container = atlanticus.get('container') if isinstance(atlanticus, dict) else None
        if container != {'command': command, 'system-profile': system_profile}:
            raise SystemExit(f'{capability.distribution} container contract is not canonical')


# Indexa módulos por ruta relativa para validar mirrors.
def _python_files(root: Path) -> dict[Path, Path]:
    return {path.relative_to(root): path for path in root.rglob('*.py')}


# Tolera __init__.py pedagógicos vacíos o con sólo docstring.
def _is_nonbehavioral_package_marker(path: Path) -> bool:
    if path.name != '__init__.py':
        return False
    tree = ast.parse(path.read_text(encoding='utf-8'))
    body = list(tree.body)
    if body and isinstance(body[0], ast.Expr):
        value = body[0].value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            body.pop(0)
    return not body


# Compara productivo y comentado por AST para permitir comentarios sin diferencias funcionales.
def _validate_mirror_pair(source_root: Path, commented_root: Path) -> None:
    source_files = _python_files(source_root)
    commented_files = _python_files(commented_root)
    missing = sorted(source_files.keys() - commented_files.keys())
    raw_extra = commented_files.keys() - source_files.keys()
    extra = sorted(
        relative
        for relative in raw_extra
        if not _is_nonbehavioral_package_marker(commented_files[relative])
    )
    if missing:
        raise SystemExit('Missing commented mirrors: ' + ', '.join(str(path) for path in missing))
    if extra:
        raise SystemExit(
            'Unexpected behavioral commented mirrors: ' + ', '.join(str(path) for path in extra)
        )
    for relative, source in sorted(source_files.items()):
        commented = commented_files[relative]
        source_ast = ast.dump(
            ast.parse(source.read_text(encoding='utf-8')), include_attributes=False
        )
        commented_ast = ast.dump(
            ast.parse(commented.read_text(encoding='utf-8')), include_attributes=False
        )
        if source_ast != commented_ast:
            raise SystemExit(f'Commented mirror mismatch: {source_root}/{relative}')


def _validate_mirrors(
    capabilities: tuple[OperationalDataCapability, ...],
    scope: Path,
    repository: Path,
) -> None:
    for capability in capabilities:
        _validate_mirror_pair(
            scope / capability.source_root,
            scope / capability.commented_root,
        )
    production = repository / 'tooling/gates/operational-data/check.py'
    commented = repository / 'tooling/gates/operational-data/commented/check.py'
    production_ast = ast.dump(
        ast.parse(production.read_text(encoding='utf-8')), include_attributes=False
    )
    commented_ast = ast.dump(
        ast.parse(commented.read_text(encoding='utf-8')), include_attributes=False
    )
    if production_ast != commented_ast:
        raise SystemExit('Operational Data gate Python mirror is not semantically equivalent')


def _run_tests(capabilities: tuple[OperationalDataCapability, ...], scope: Path) -> None:
    for capability in capabilities:
        print(f'[tests] {capability.key}', flush=True)
        _run(
            [sys.executable, '-m', 'pytest', 'tests', '-ra'],
            cwd=scope / capability.project_root,
        )


def _validate_imports(capabilities: tuple[OperationalDataCapability, ...], scope: Path) -> None:
    for capability in capabilities:
        _run([sys.executable, '-c', f'import {capability.import_name}'], cwd=scope)


def _canonical_distribution_name(value: str) -> str:
    return re.sub(r'[-_.]+', '-', value).lower()


def _wheel_metadata(archive: ZipFile) -> tuple[str, str]:
    metadata_files = [name for name in archive.namelist() if name.endswith('.dist-info/METADATA')]
    if len(metadata_files) != 1:
        raise SystemExit('Expected exactly one METADATA file in wheel')
    metadata = archive.read(metadata_files[0]).decode('utf-8')
    name = None
    version = None
    for line in metadata.splitlines():
        if line.startswith('Name: '):
            name = line.removeprefix('Name: ').strip()
        elif line.startswith('Version: '):
            version = line.removeprefix('Version: ').strip()
        if name is not None and version is not None:
            break
    if not name or not version:
        raise SystemExit('Wheel METADATA is missing Name or Version')
    return name, version


# Construye wheels y valida identidad/versión desde METADATA contra cada pyproject.
def _build_wheels(capabilities: tuple[OperationalDataCapability, ...], scope: Path) -> None:
    dist = scope / 'dist'
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir(parents=True)
    for capability in capabilities:
        expected_version = _project_version(
            scope / capability.project_root, capability.distribution
        )
        before = set(dist.glob('*.whl'))
        _run(
            ['uv', 'build', capability.project_root, '--wheel', '--out-dir', str(dist)],
            cwd=scope,
        )
        wheels = tuple(set(dist.glob('*.whl')) - before)
        if len(wheels) != 1:
            raise SystemExit(f'Expected exactly one new wheel for {capability.distribution}')
        wheel = wheels[0]
        typed_path = capability.import_name.replace('.', '/') + '/py.typed'
        with ZipFile(wheel) as archive:
            names = set(archive.namelist())
            metadata_name, metadata_version = _wheel_metadata(archive)
        if _canonical_distribution_name(metadata_name) != _canonical_distribution_name(
            capability.distribution
        ):
            raise SystemExit(
                f'Unexpected wheel distribution: expected {capability.distribution}, found {metadata_name}'
            )
        if metadata_version != expected_version:
            raise SystemExit(
                f'Unexpected wheel version for {capability.distribution}: '
                f'expected {expected_version}, found {metadata_version}'
            )
        if typed_path not in names:
            raise SystemExit(f'Missing py.typed in wheel: {capability.distribution}')
        if any('/tests/' in name or '/commented/' in name for name in names):
            raise SystemExit(f'Non-productive files found in wheel: {capability.distribution}')


# Ejecuta el gate completo; no depende de artifacts ni de .runtime.
def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    arguments = _parser().parse_args(raw_argv)
    capabilities = _resolve_capabilities(arguments)
    _bootstrap(raw_argv, clean=arguments.clean)
    repository = _repository_root()
    scope = _scope_root()
    print('Atlanticus Operational Data capabilities:', ', '.join(item.key for item in capabilities))
    print('[1/10] Validating Python runtime')
    _validate_python()
    print('[2/10] Validating scope workspace composition')
    _validate_workspace(scope, repository)
    print('[3/10] Validating dependency and version correlation')
    _validate_dependency_correlation(scope, repository)
    print('[4/10] Validating ownership and process contracts')
    _validate_retired_paths(repository)
    _validate_ownership(scope)
    _validate_process_isolation(scope)
    _validate_process_contracts(scope)
    print('[5/10] Validating locked dependency graph')
    _run(['uv', 'lock', '--check'], cwd=scope)
    targets = [capability.project_root for capability in capabilities]
    targets.extend(
        [
            str(repository / 'tooling/gates/operational-data/check.py'),
            str(repository / 'tooling/gates/operational-data/commented/check.py'),
        ]
    )
    print('[6/10] Applying safe Ruff fixes and formatting')
    _run([sys.executable, '-m', 'ruff', 'check', '--fix', *targets], cwd=scope)
    _run([sys.executable, '-m', 'ruff', 'format', *targets], cwd=scope)
    _run([sys.executable, '-m', 'ruff', 'check', *targets], cwd=scope)
    _run([sys.executable, '-m', 'ruff', 'format', '--check', *targets], cwd=scope)
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
