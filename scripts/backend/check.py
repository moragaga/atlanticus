from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

EXPECTED_PYTHON_VERSION = '3.14.2'


@dataclass(frozen=True, slots=True)
class BackendCapability:
    key: str
    distribution: str
    import_name: str
    project_root: str
    tests_root: str
    source_root: str
    commented_root: str


CAPABILITIES: dict[str, BackendCapability] = {
    'kernel': BackendCapability(
        'kernel',
        'atlanticus-kernel',
        'atlanticus.kernel',
        'kernel',
        'kernel/tests',
        'kernel/src',
        'kernel/commented',
    ),
    'json': BackendCapability(
        'json',
        'atlanticus-json',
        'atlanticus.json',
        'json',
        'json/tests',
        'json/src',
        'json/commented',
    ),
    'configuration': BackendCapability(
        'configuration',
        'atlanticus-configuration',
        'atlanticus.configuration',
        'configuration',
        'configuration/tests',
        'configuration/src',
        'configuration/commented',
    ),
    'datasets': BackendCapability(
        'datasets',
        'atlanticus-datasets',
        'atlanticus.datasets',
        'datasets',
        'datasets/tests',
        'datasets/src',
        'datasets/commented',
    ),
    'datasets-parquet': BackendCapability(
        'datasets-parquet',
        'atlanticus-datasets-parquet',
        'atlanticus.datasets.parquet',
        'datasets-parquet',
        'datasets-parquet/tests',
        'datasets-parquet/src',
        'datasets-parquet/commented',
    ),
    'datasets-runtime': BackendCapability(
        'datasets-runtime',
        'atlanticus-datasets-runtime',
        'atlanticus.datasets.runtime',
        'datasets-runtime',
        'datasets-runtime/tests',
        'datasets-runtime/src',
        'datasets-runtime/commented',
    ),
    'observability': BackendCapability(
        'observability',
        'atlanticus-observability',
        'atlanticus.observability',
        'observability',
        'observability/tests',
        'observability/src',
        'observability/commented',
    ),
    'observability-azure': BackendCapability(
        'observability-azure',
        'atlanticus-observability-azure',
        'atlanticus.observability_azure',
        'observability-azure',
        'observability-azure/tests',
        'observability-azure/src',
        'observability-azure/commented',
    ),
    'state': BackendCapability(
        'state',
        'atlanticus-state',
        'atlanticus.state',
        'state',
        'state/tests',
        'state/src',
        'state/commented',
    ),
    'runtime': BackendCapability(
        'runtime',
        'atlanticus-job-runtime',
        'atlanticus.runtime',
        'runtime',
        'runtime/tests',
        'runtime/src',
        'runtime/commented',
    ),
}


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _backend_root() -> Path:
    return _repository_root() / 'backend'


def _run(command: list[str], *, cwd: Path) -> None:
    print('>', ' '.join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Validate Atlanticus Backend capabilities by semantic target.',
    )
    parser.add_argument(
        'capabilities',
        nargs='*',
        help='Capabilities to validate. No arguments means all registered Backend capabilities.',
    )
    parser.add_argument('--all', action='store_true', help='Validate all registered capabilities.')
    parser.add_argument(
        '--list', action='store_true', help='List registered capabilities and exit.'
    )
    return parser


def _resolve_capabilities(arguments: argparse.Namespace) -> tuple[BackendCapability, ...]:
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
            f'Unknown Backend capabilities: {", ".join(unknown)}. Valid capabilities: {valid}'
        )

    unique: list[BackendCapability] = []
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


def _project_metadata(path: Path) -> dict[str, object]:
    with path.open('rb') as stream:
        document = tomllib.load(stream)
    project = document.get('project')
    if not isinstance(project, dict):
        raise SystemExit(f'Missing [project] table: {path}')
    return project


def _dependency_name(requirement: str) -> str:
    for separator in ('==', '>=', '<=', '~=', '!=', '>', '<', ';', '['):
        if separator in requirement:
            return requirement.split(separator, 1)[0].strip()
    return requirement.strip()


def _internal_requirements(project: dict[str, object]) -> tuple[str, ...]:
    requirements: list[str] = []
    dependencies = project.get('dependencies', [])
    if isinstance(dependencies, list):
        requirements.extend(item for item in dependencies if isinstance(item, str))
    optional = project.get('optional-dependencies', {})
    if isinstance(optional, dict):
        for values in optional.values():
            if isinstance(values, list):
                requirements.extend(item for item in values if isinstance(item, str))
    internal = set(capability.distribution for capability in CAPABILITIES.values())
    return tuple(item for item in requirements if _dependency_name(item) in internal)


def _validate_internal_version_correlation(backend: Path) -> None:
    versions: dict[str, str] = {}
    projects: dict[str, dict[str, object]] = {}
    for capability in CAPABILITIES.values():
        project = _project_metadata(backend / capability.project_root / 'pyproject.toml')
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

    for distribution, project in projects.items():
        for requirement in _internal_requirements(project):
            dependency = _dependency_name(requirement)
            expected = f'{dependency}=={versions[dependency]}'
            if requirement != expected:
                raise SystemExit(
                    f'Internal dependency mismatch in {distribution}: expected {expected}, found {requirement}'
                )


def _validate_mirrors(
    capabilities: tuple[BackendCapability, ...],
    *,
    root: Path,
    backend: Path,
) -> None:
    validator = root / 'scripts/repository/validate_mirrors.py'
    arguments = [sys.executable, str(validator)]
    for capability in capabilities:
        arguments.extend((capability.source_root, capability.commented_root))
    arguments.extend(
        (
            str(root / 'scripts/backend'),
            str(root / 'scripts/commented/backend'),
        )
    )
    _run(arguments, cwd=backend)


def _ruff_targets(
    capabilities: tuple[BackendCapability, ...],
    *,
    root: Path,
) -> list[str]:
    targets = [capability.project_root for capability in capabilities]
    targets.extend(
        (
            str(root / 'scripts/backend/check.py'),
            str(root / 'scripts/commented/backend/check.py'),
            str(root / 'scripts/repository/validate_mirrors.py'),
            str(root / 'scripts/commented/repository/validate_mirrors.py'),
        )
    )
    return list(dict.fromkeys(targets))


def _validate_lock(backend: Path) -> None:
    _run(['uv', 'lock', '--check'], cwd=backend)


def _run_tests(capabilities: tuple[BackendCapability, ...], *, backend: Path) -> None:
    for capability in capabilities:
        project = backend / capability.project_root
        print(f'[tests] {capability.key}', flush=True)
        _run([sys.executable, '-m', 'pytest', 'tests'], cwd=project)


def _build_wheels(capabilities: tuple[BackendCapability, ...], *, backend: Path) -> None:
    dist = backend / 'dist'
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
            cwd=backend,
        )

    wheels = tuple(dist.glob('*.whl'))
    if len(wheels) != len(capabilities):
        raise SystemExit(f'Expected {len(capabilities)} wheels in {dist}, found {len(wheels)}')


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    capabilities = _resolve_capabilities(arguments)
    root = _repository_root()
    backend = _backend_root()
    names = ', '.join(capability.key for capability in capabilities)

    print(f'Atlanticus Backend capabilities: {names}')

    print('[1/8] Validating Python runtime')
    _validate_python_version()

    print('[2/8] Validating internal dependency correlation')
    _validate_internal_version_correlation(backend)

    print('[3/8] Validating locked dependency graph')
    _validate_lock(backend)

    targets = _ruff_targets(capabilities, root=root)
    print('[4/8] Applying safe Ruff fixes and formatting')
    _run(['ruff', 'check', '--fix', *targets], cwd=backend)
    _run(['ruff', 'format', *targets], cwd=backend)
    _run(['ruff', 'check', *targets], cwd=backend)
    _run(['ruff', 'format', '--check', *targets], cwd=backend)

    print('[5/8] Running selected Backend tests by capability')
    _run_tests(capabilities, backend=backend)

    print('[6/8] Validating productive/commented semantic mirrors')
    _validate_mirrors(capabilities, root=root, backend=backend)

    print('[7/8] Validating public imports')
    for capability in capabilities:
        _run([sys.executable, '-c', f'import {capability.import_name}'], cwd=backend)

    print('[8/8] Building selected Backend wheels')
    _build_wheels(capabilities, backend=backend)

    print(f'Atlanticus Backend validated: {names}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
