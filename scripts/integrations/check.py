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
class IntegrationCapability:
    key: str
    distribution: str
    import_name: str
    project_root: str
    source_root: str
    commented_root: str
    local_integration_root: str | None = None


CAPABILITIES: dict[str, IntegrationCapability] = {
    'pi-contracts': IntegrationCapability(
        'pi-contracts',
        'atlanticus-pi-contracts',
        'atlanticus.integrations.pi.contracts',
        'pi/contracts',
        'pi/contracts/src',
        'pi/contracts/commented',
    ),
    'pi-web-api': IntegrationCapability(
        'pi-web-api',
        'atlanticus-pi-web-api',
        'atlanticus.integrations.pi.web_api',
        'pi/web-api',
        'pi/web-api/src',
        'pi/web-api/commented',
        'tests/integration/local',
    ),
}

CROSS_WORKSPACE_SOURCES = {
    'atlanticus-http': '../connectivity/http-client',
    'atlanticus-observability': '../backend/observability',
    'atlanticus-kernel': '../backend/kernel',
}

EXPECTED_EXTERNAL_VERSIONS = {
    'atlanticus-http': '1.0.0',
    'atlanticus-observability': '1.0.0',
    'atlanticus-kernel': '1.0.0',
}


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _integrations_root() -> Path:
    return _repository_root() / 'integrations'


def _run(command: list[str], *, cwd: Path) -> None:
    print('>', ' '.join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Validate Atlanticus Integrations capabilities.')
    parser.add_argument('capabilities', nargs='*')
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--list', action='store_true')
    return parser


def _resolve_capabilities(arguments: argparse.Namespace) -> tuple[IntegrationCapability, ...]:
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
            f'Unknown Integrations capabilities: {", ".join(unknown)}. '
            f'Valid capabilities: {", ".join(CAPABILITIES)}'
        )
    seen: set[str] = set()
    resolved: list[IntegrationCapability] = []
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


def _validate_workspace(integrations: Path, repository: Path) -> None:
    document = _read_toml(integrations / 'pyproject.toml')
    tool = document.get('tool')
    if not isinstance(tool, dict):
        raise SystemExit('Missing [tool] configuration in integrations/pyproject.toml')
    uv = tool.get('uv')
    if not isinstance(uv, dict):
        raise SystemExit('Missing [tool.uv] configuration in integrations/pyproject.toml')
    workspace = uv.get('workspace')
    expected_members = ['pi/contracts', 'pi/web-api']
    if not isinstance(workspace, dict) or workspace.get('members') != expected_members:
        raise SystemExit('Integrations workspace members must be pi/contracts and pi/web-api')
    sources = uv.get('sources')
    if not isinstance(sources, dict):
        raise SystemExit('Missing [tool.uv.sources] in integrations/pyproject.toml')
    for distribution, expected_path in CROSS_WORKSPACE_SOURCES.items():
        source = sources.get(distribution)
        if not isinstance(source, dict):
            raise SystemExit(f'Missing UV source for {distribution}')
        if source.get('path') != expected_path or source.get('editable') is not True:
            raise SystemExit(
                f'UV source for {distribution} must be path={expected_path!r} and editable=true'
            )
        target = (integrations / expected_path).resolve()
        try:
            target.relative_to(repository.resolve())
        except ValueError as exc:
            raise SystemExit(f'UV source escapes repository: {distribution}') from exc
        if not (target / 'pyproject.toml').is_file():
            raise SystemExit(f'UV source target is missing: {distribution} -> {target}')


def _require_version(project_root: Path, distribution: str, expected: str) -> None:
    project = _project(project_root / 'pyproject.toml')
    if project.get('name') != distribution:
        raise SystemExit(f'Unexpected distribution at {project_root}: {project.get("name")!r}')
    if project.get('version') != expected:
        raise SystemExit(f'{distribution} must be version {expected}')


def _validate_dependency_correlation(integrations: Path, repository: Path) -> None:
    for capability in CAPABILITIES.values():
        _require_version(integrations / capability.project_root, capability.distribution, '1.0.0')
    web_api = _project(integrations / 'pi/web-api/pyproject.toml')
    dependencies = web_api.get('dependencies')
    if dependencies != ['atlanticus-http==1.0.0']:
        raise SystemExit('atlanticus-pi-web-api must depend exactly on atlanticus-http==1.0.0')
    external_paths = {
        'atlanticus-http': repository / 'connectivity/http-client',
        'atlanticus-observability': repository / 'backend/observability',
        'atlanticus-kernel': repository / 'backend/kernel',
    }
    for distribution, expected in EXPECTED_EXTERNAL_VERSIONS.items():
        _require_version(external_paths[distribution], distribution, expected)


def _validate_mirrors(
    capabilities: tuple[IntegrationCapability, ...],
    integrations: Path,
    repository: Path,
) -> None:
    arguments: list[str] = []
    for capability in capabilities:
        arguments.extend([capability.source_root, capability.commented_root])
    arguments.extend(
        [
            str(repository / 'scripts/integrations'),
            str(repository / 'scripts/commented/integrations'),
        ]
    )
    command = [
        sys.executable,
        str(repository / 'scripts/repository/validate_mirrors.py'),
        *arguments,
    ]
    _run(command, cwd=integrations)


def _run_tests(capabilities: tuple[IntegrationCapability, ...], integrations: Path) -> None:
    for capability in capabilities:
        project = integrations / capability.project_root
        print(f'[tests] {capability.key}', flush=True)
        _run([sys.executable, '-m', 'pytest', 'tests/unit'], cwd=project)
        if capability.local_integration_root is not None:
            print(f'[integration-local] {capability.key}', flush=True)
            _run([sys.executable, '-m', 'pytest', capability.local_integration_root], cwd=project)


def _validate_imports(capabilities: tuple[IntegrationCapability, ...], integrations: Path) -> None:
    for capability in capabilities:
        _run([sys.executable, '-c', f'import {capability.import_name}'], cwd=integrations)


def _build_wheels(capabilities: tuple[IntegrationCapability, ...], integrations: Path) -> None:
    dist = integrations / 'dist'
    if dist.exists():
        shutil.rmtree(dist)
    dist.mkdir(parents=True)
    for capability in capabilities:
        command = ['uv', 'build', capability.project_root, '--wheel', '--out-dir', str(dist)]
        _run(command, cwd=integrations)
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
    integrations = _integrations_root()
    print('Atlanticus Integrations capabilities:', ', '.join(item.key for item in capabilities))
    print('[1/9] Validating Python runtime')
    _validate_python()
    print('[2/9] Validating workspace composition')
    _validate_workspace(integrations, repository)
    print('[3/9] Validating dependency and version correlation')
    _validate_dependency_correlation(integrations, repository)
    print('[4/9] Validating locked dependency graph')
    _run(['uv', 'lock', '--check'], cwd=integrations)
    targets = [capability.project_root for capability in capabilities]
    targets.extend(
        [
            str(repository / 'scripts/integrations/check.py'),
            str(repository / 'scripts/commented/integrations/check.py'),
            str(repository / 'scripts/repository/validate_mirrors.py'),
            str(repository / 'scripts/commented/repository/validate_mirrors.py'),
        ]
    )
    print('[5/9] Applying safe Ruff fixes and formatting')
    _run(['ruff', 'check', '--fix', *targets], cwd=integrations)
    _run(['ruff', 'format', *targets], cwd=integrations)
    _run(['ruff', 'check', *targets], cwd=integrations)
    _run(['ruff', 'format', '--check', *targets], cwd=integrations)
    print('[6/9] Running selected Integrations tests by capability')
    _run_tests(capabilities, integrations)
    print('[7/9] Validating productive/commented semantic mirrors')
    _validate_mirrors(capabilities, integrations, repository)
    print('[8/9] Validating public imports')
    _validate_imports(capabilities, integrations)
    print('[9/9] Building selected Integrations wheels')
    _build_wheels(capabilities, integrations)
    print('Atlanticus Integrations validated:', ', '.join(item.key for item in capabilities))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
