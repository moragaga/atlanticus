from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

# El gate se ejecuta únicamente sobre la versión autoritativa del proyecto.
EXPECTED_PYTHON_VERSION = '3.14.2'


@dataclass(frozen=True, slots=True)
class ConnectivityCapability:
    key: str
    distribution: str
    import_name: str
    project_root: str
    source_root: str
    commented_root: str
    docker_compose: str | None = None
    docker_exit_service: str | None = None
    docker_image: str | None = None
    docker_logs: tuple[str, ...] = ()


# El catálogo mantiene identidad, import público y assets de integración por capability.
CAPABILITIES: dict[str, ConnectivityCapability] = {
    'http-client': ConnectivityCapability(
        'http-client',
        'atlanticus-http',
        'atlanticus.connectivity.http',
        'http-client',
        'http-client/src',
        'http-client/commented',
        'docker/http/compose.yaml',
        'http-integration',
        'atlanticus-http-integration:local',
        ('http-fake-api', 'http-integration'),
    ),
    'key-vault': ConnectivityCapability(
        'key-vault',
        'atlanticus-key-vault',
        'atlanticus.connectivity.key_vault',
        'key-vault',
        'key-vault/src',
        'key-vault/commented',
    ),
    'cosmos': ConnectivityCapability(
        'cosmos',
        'atlanticus-cosmos',
        'atlanticus.connectivity.cosmos',
        'cosmos',
        'cosmos/src',
        'cosmos/commented',
        'docker/cosmos/compose.yaml',
        'cosmos-integration',
        'atlanticus-cosmos-integration:local',
        ('cosmos-emulator', 'cosmos-integration'),
    ),
    'service-bus': ConnectivityCapability(
        'service-bus',
        'atlanticus-service-bus',
        'atlanticus.connectivity.service_bus',
        'service-bus',
        'service-bus/src',
        'service-bus/commented',
        'docker/service-bus/compose.yaml',
        'service-bus-integration',
        'atlanticus-service-bus-integration:local',
        ('servicebus-mssql', 'servicebus-emulator', 'service-bus-integration'),
    ),
    'sql': ConnectivityCapability(
        'sql',
        'atlanticus-sql',
        'atlanticus.connectivity.sql',
        'sql',
        'sql/src',
        'sql/commented',
        'docker/sql/compose.yaml',
        'sql-integration',
        'atlanticus-sql-integration:local',
        ('sql-server', 'sql-integration'),
    ),
    'storage': ConnectivityCapability(
        'storage',
        'atlanticus-storage',
        'atlanticus.connectivity.storage',
        'storage',
        'storage/src',
        'storage/commented',
        'docker/storage/compose.yaml',
        'storage-integration',
        'atlanticus-storage-integration:local',
        ('azurite', 'storage-integration'),
    ),
    'redis': ConnectivityCapability(
        'redis',
        'atlanticus-redis',
        'atlanticus.connectivity.redis',
        'redis',
        'redis/src',
        'redis/commented',
        'docker/redis/compose.yaml',
        'redis-integration',
        'atlanticus-redis-integration:local',
        ('redis-server', 'redis-integration'),
    ),
}

AZURE_LOCAL_CAPABILITIES = frozenset({'key-vault', 'storage', 'cosmos', 'redis'})


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _connectivity_root() -> Path:
    return _repository_root() / 'connectivity'


def _run(
    command: list[str],
    *,
    cwd: Path,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    print('>', ' '.join(command), flush=True)
    return subprocess.run(command, cwd=cwd, check=check, env=env)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Validate Atlanticus Connectivity capabilities by semantic target.',
    )
    parser.add_argument(
        'capabilities',
        nargs='*',
        help='Capabilities to validate. No arguments means all registered Connectivity capabilities.',
    )
    parser.add_argument('--all', action='store_true', help='Validate all registered capabilities.')
    parser.add_argument(
        '--list', action='store_true', help='List registered capabilities and exit.'
    )
    parser.add_argument(
        '--docker',
        action='store_true',
        help='Run local Docker integrations for selected capabilities that provide them.',
    )
    parser.add_argument(
        '--azure-local',
        action='store_true',
        help='Run the Floci-AZ cross-validation for supported selected capabilities.',
    )
    return parser


def _resolve_capabilities(arguments: argparse.Namespace) -> tuple[ConnectivityCapability, ...]:
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
        valid = ', '.join(CAPABILITIES)
        raise SystemExit(
            f'Unknown Connectivity capabilities: {", ".join(unknown)}. Valid capabilities: {valid}'
        )

    unique: list[ConnectivityCapability] = []
    seen: set[str] = set()
    for key in requested:
        if key not in seen:
            unique.append(CAPABILITIES[key])
            seen.add(key)
    return tuple(unique)


def _validate_python_version() -> None:
    version = platform.python_version()
    if version != EXPECTED_PYTHON_VERSION:
        raise SystemExit(f'Expected Python {EXPECTED_PYTHON_VERSION}, found {version}')


def _read_toml(path: Path) -> dict[str, object]:
    with path.open('rb') as stream:
        return tomllib.load(stream)


def _project_metadata(path: Path) -> dict[str, object]:
    document = _read_toml(path)
    project = document.get('project')
    if not isinstance(project, dict):
        raise SystemExit(f'Missing [project] table: {path}')
    return project


def _dependency_name(requirement: str) -> str:
    for separator in ('==', '>=', '<=', '~=', '!=', '>', '<', ';', '['):
        if separator in requirement:
            return requirement.split(separator, 1)[0].strip()
    return requirement.strip()


# Verifica que el workspace declare exactamente las capabilities y sources que realmente consume.
def _validate_workspace(connectivity: Path, root: Path) -> None:
    document = _read_toml(connectivity / 'pyproject.toml')
    tool = document.get('tool')
    if not isinstance(tool, dict):
        raise SystemExit('Missing [tool] configuration in connectivity/pyproject.toml')
    uv = tool.get('uv')
    if not isinstance(uv, dict):
        raise SystemExit('Missing [tool.uv] configuration in connectivity/pyproject.toml')
    sources = uv.get('sources')
    workspace = uv.get('workspace')
    if not isinstance(sources, dict) or not isinstance(workspace, dict):
        raise SystemExit('Connectivity workspace sources or members are missing')

    expected_members = [capability.project_root for capability in CAPABILITIES.values()]
    if workspace.get('members') != expected_members:
        raise SystemExit('Connectivity workspace members do not match registered capabilities')

    expected_backend_sources = {
        'atlanticus-kernel': '../backend/kernel',
        'atlanticus-observability': '../backend/observability',
    }
    for distribution, expected_path in expected_backend_sources.items():
        value = sources.get(distribution)
        if not isinstance(value, dict) or value.get('path') != expected_path:
            raise SystemExit(f'Unexpected workspace source for {distribution}')
        if value.get('editable') is not True:
            raise SystemExit(
                f'Connectivity backend source must declare editable = true: {distribution}'
            )
        if not (root / 'backend' / Path(expected_path).name).exists():
            raise SystemExit(f'Missing Backend dependency source: {distribution}')

    for capability in CAPABILITIES.values():
        value = sources.get(capability.distribution)
        if not isinstance(value, dict) or value.get('workspace') is not True:
            raise SystemExit(
                f'Connectivity workspace source is not registered: {capability.distribution}'
            )


# Toda dependencia Atlanticus debe apuntar exactamente a la versión declarada por su owner local.
def _validate_internal_version_correlation(connectivity: Path, root: Path) -> None:
    backend_distributions = {
        'atlanticus-kernel': root / 'backend/kernel/pyproject.toml',
        'atlanticus-observability': root / 'backend/observability/pyproject.toml',
    }
    versions: dict[str, str] = {}
    for distribution, path in backend_distributions.items():
        project = _project_metadata(path)
        name = project.get('name')
        version = project.get('version')
        if name != distribution or not isinstance(version, str) or not version:
            raise SystemExit(f'Invalid Backend dependency metadata: {distribution}')
        versions[distribution] = version

    projects: dict[str, dict[str, object]] = {}
    for capability in CAPABILITIES.values():
        project = _project_metadata(connectivity / capability.project_root / 'pyproject.toml')
        name = project.get('name')
        version = project.get('version')
        if name != capability.distribution:
            raise SystemExit(
                f'Unexpected distribution for {capability.key}: expected {capability.distribution}, found {name}'
            )
        if not isinstance(version, str) or not version:
            raise SystemExit(f'Missing version for {capability.distribution}')
        versions[capability.distribution] = version
        projects[capability.distribution] = project

    internal = set(versions)
    for distribution, project in projects.items():
        dependencies = project.get('dependencies', [])
        if not isinstance(dependencies, list):
            continue
        for requirement in dependencies:
            if not isinstance(requirement, str):
                continue
            dependency = _dependency_name(requirement)
            if dependency not in internal:
                continue
            expected = f'{dependency}=={versions[dependency]}'
            if requirement != expected:
                raise SystemExit(
                    f'Internal dependency mismatch in {distribution}: expected {expected}, found {requirement}'
                )


def _validate_lock(connectivity: Path) -> None:
    _run(['uv', 'lock', '--check'], cwd=connectivity)


def _ruff_targets(
    capabilities: tuple[ConnectivityCapability, ...],
    *,
    root: Path,
) -> list[str]:
    targets = [capability.project_root for capability in capabilities]
    targets.extend(
        (
            str(root / 'scripts/connectivity/check.py'),
            str(root / 'scripts/commented/connectivity/check.py'),
            str(root / 'scripts/repository/validate_mirrors.py'),
            str(root / 'scripts/commented/repository/validate_mirrors.py'),
        )
    )
    return list(dict.fromkeys(targets))


# Cada suite se ejecuta desde la raíz de su package para evitar contaminación entre namespaces compartidos.
def _run_tests(
    capabilities: tuple[ConnectivityCapability, ...],
    *,
    connectivity: Path,
) -> None:
    for capability in capabilities:
        project = connectivity / capability.project_root
        print(f'[tests] {capability.key}', flush=True)
        _run([sys.executable, '-m', 'pytest', 'tests/unit'], cwd=project)


# El validador transversal compara AST productivo y espejo comentado.
def _validate_mirrors(
    capabilities: tuple[ConnectivityCapability, ...],
    *,
    root: Path,
    connectivity: Path,
) -> None:
    validator = root / 'scripts/repository/validate_mirrors.py'
    arguments = [sys.executable, str(validator)]
    for capability in capabilities:
        arguments.extend((capability.source_root, capability.commented_root))
    arguments.extend(
        (
            str(root / 'scripts/connectivity'),
            str(root / 'scripts/commented/connectivity'),
        )
    )
    _run(arguments, cwd=connectivity)


def _build_wheels(
    capabilities: tuple[ConnectivityCapability, ...],
    *,
    connectivity: Path,
) -> None:
    dist = connectivity / 'dist'
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir()

    for capability in capabilities:
        _run(
            [
                'uv',
                'build',
                capability.project_root,
                '--wheel',
                '--out-dir',
                str(dist),
            ],
            cwd=connectivity,
        )

    wheels = tuple(dist.glob('*.whl'))
    if len(wheels) != len(capabilities):
        raise SystemExit(f'Expected {len(capabilities)} wheels in {dist}, found {len(wheels)}')


def _docker_required() -> None:
    if shutil.which('docker') is None:
        raise SystemExit('docker is required for Connectivity integration tests')


# Las integraciones Docker son opt-in y limpian siempre sus recursos al terminar.
def _run_docker_integration(
    capability: ConnectivityCapability,
    *,
    connectivity: Path,
) -> None:
    if capability.docker_compose is None or capability.docker_exit_service is None:
        print(
            f'[docker] {capability.key}: no specialized local Docker integration; use --azure-local when supported',
            flush=True,
        )
        return

    compose = ['docker', 'compose', '-f', capability.docker_compose]
    _run([*compose, 'down', '-v', '--remove-orphans'], cwd=connectivity, check=False)
    if capability.docker_image is not None:
        _run(['docker', 'image', 'rm', capability.docker_image], cwd=connectivity, check=False)

    result = _run(
        [
            *compose,
            'up',
            '--build',
            '--abort-on-container-exit',
            '--exit-code-from',
            capability.docker_exit_service,
        ],
        cwd=connectivity,
        check=False,
    )
    if result.returncode != 0 and capability.docker_logs:
        _run([*compose, 'logs', *capability.docker_logs], cwd=connectivity, check=False)
    _run([*compose, 'down', '-v', '--remove-orphans'], cwd=connectivity, check=False)
    if capability.docker_image is not None:
        _run(['docker', 'image', 'rm', capability.docker_image], cwd=connectivity, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def _run_docker_integrations(
    capabilities: tuple[ConnectivityCapability, ...],
    *,
    connectivity: Path,
) -> None:
    _docker_required()
    for capability in capabilities:
        print(f'[docker] {capability.key}', flush=True)
        _run_docker_integration(capability, connectivity=connectivity)


# Floci-AZ sigue siendo una validación local; no implica despliegue ni qualification en Azure.
def _run_azure_local(
    capabilities: tuple[ConnectivityCapability, ...],
    *,
    connectivity: Path,
) -> None:
    selected = [
        capability.key for capability in capabilities if capability.key in AZURE_LOCAL_CAPABILITIES
    ]
    if not selected:
        print('[azure-local] No selected capabilities provide Floci-AZ validation', flush=True)
        return

    _docker_required()
    target = 'all' if set(selected) == AZURE_LOCAL_CAPABILITIES else ','.join(selected)
    compose_file = 'docker/azure-local/compose.yaml'
    compose = ['docker', 'compose', '-f', compose_file]
    runner_image = 'atlanticus-connectivity-azure-local-integration:local'

    _run([*compose, 'down', '-v', '--remove-orphans'], cwd=connectivity, check=False)
    _run(['docker', 'image', 'rm', runner_image], cwd=connectivity, check=False)
    environment = os.environ.copy()
    environment['ATLANTICUS_AZURE_LOCAL_TARGET'] = target
    result = _run(
        [
            *compose,
            'up',
            '--build',
            '--abort-on-container-exit',
            '--exit-code-from',
            'connectivity-integration',
        ],
        cwd=connectivity,
        check=False,
        env=environment,
    )
    if result.returncode != 0:
        _run(
            [*compose, 'logs', 'floci-az', 'connectivity-integration'],
            cwd=connectivity,
            check=False,
        )
    _run([*compose, 'down', '-v', '--remove-orphans'], cwd=connectivity, check=False)
    _run(['docker', 'image', 'rm', runner_image], cwd=connectivity, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    print(f'Azure-local Connectivity validation passed: {" ".join(selected)}')


# El flujo por defecto cubre contrato local; Docker y Azure-local se agregan sólo cuando se solicitan.
def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    capabilities = _resolve_capabilities(arguments)
    root = _repository_root()
    connectivity = _connectivity_root()
    names = ', '.join(capability.key for capability in capabilities)

    print(f'Atlanticus Connectivity capabilities: {names}')

    print('[1/9] Validating Python runtime')
    _validate_python_version()

    print('[2/9] Validating workspace composition')
    _validate_workspace(connectivity, root)

    print('[3/9] Validating internal dependency correlation')
    _validate_internal_version_correlation(connectivity, root)

    print('[4/9] Validating locked dependency graph')
    _validate_lock(connectivity)

    targets = _ruff_targets(capabilities, root=root)
    print('[5/9] Applying safe Ruff fixes and formatting')
    _run(['ruff', 'check', '--fix', *targets], cwd=connectivity)
    _run(['ruff', 'format', *targets], cwd=connectivity)
    _run(['ruff', 'check', *targets], cwd=connectivity)
    _run(['ruff', 'format', '--check', *targets], cwd=connectivity)

    print('[6/9] Running selected Connectivity unit tests by capability')
    _run_tests(capabilities, connectivity=connectivity)

    print('[7/9] Validating productive/commented semantic mirrors')
    _validate_mirrors(capabilities, root=root, connectivity=connectivity)

    print('[8/9] Validating public imports')
    for capability in capabilities:
        _run([sys.executable, '-c', f'import {capability.import_name}'], cwd=connectivity)

    print('[9/9] Building selected Connectivity wheels')
    _build_wheels(capabilities, connectivity=connectivity)

    if arguments.docker:
        _run_docker_integrations(capabilities, connectivity=connectivity)
    if arguments.azure_local:
        _run_azure_local(capabilities, connectivity=connectivity)

    print(f'Atlanticus Connectivity validated: {names}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
