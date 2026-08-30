from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

EXPECTED_PYTHON_VERSION = '3.14.2'


@dataclass(frozen=True, slots=True)
class AdaCapability:
    key: str
    project_root: str
    ruff_roots: tuple[str, ...]
    tests_root: str
    source_root: str
    commented_root: str


CAPABILITIES: dict[str, AdaCapability] = {
    'kpi-definition': AdaCapability(
        key='kpi-definition',
        project_root='scopes/ada/web/configuration/kpi-definition',
        ruff_roots=('src', 'tests', 'commented'),
        tests_root='tests',
        source_root='src',
        commented_root='commented',
    ),
    'kpi-inspection-core': AdaCapability(
        key='kpi-inspection-core',
        project_root='scopes/ada/web/inspection/core',
        ruff_roots=('src', 'tests', 'commented'),
        tests_root='tests',
        source_root='src',
        commented_root='commented',
    ),
    'kpi-inspection-definition-provider': AdaCapability(
        key='kpi-inspection-definition-provider',
        project_root='scopes/ada/web/inspection/providers/kpi-definition',
        ruff_roots=('src', 'tests', 'commented'),
        tests_root='tests',
        source_root='src',
        commented_root='commented',
    ),
    'kpi-inspection-portability': AdaCapability(
        key='kpi-inspection-portability',
        project_root='scopes/ada/web/inspection/portability',
        ruff_roots=('src', 'tests', 'commented'),
        tests_root='tests',
        source_root='src',
        commented_root='commented',
    ),
    'kpi-inspection-surface': AdaCapability(
        key='kpi-inspection-surface',
        project_root='scopes/ada/web/inspection/surface',
        ruff_roots=('src', 'tests', 'commented'),
        tests_root='tests',
        source_root='src',
        commented_root='commented',
    ),
    'kpi-inspection-interval-resilience': AdaCapability(
        key='kpi-inspection-interval-resilience',
        project_root='scopes/ada/web/inspection/interval-resilience',
        ruff_roots=('src', 'tests', 'commented'),
        tests_root='tests',
        source_root='src',
        commented_root='commented',
    ),
    'kpi-inspection-empty-definition-flow': AdaCapability(
        key='kpi-inspection-empty-definition-flow',
        project_root='scopes/ada/web/inspection/empty-definition-flow',
        ruff_roots=('src', 'tests', 'commented'),
        tests_root='tests',
        source_root='src',
        commented_root='commented',
    ),
    'kpi-inspection-runtime': AdaCapability(
        key='kpi-inspection-runtime',
        project_root='scopes/ada/web/inspection/runtime',
        ruff_roots=('src', 'tests', 'commented'),
        tests_root='tests',
        source_root='src',
        commented_root='commented',
    ),
    'kpi-inspection-api': AdaCapability(
        key='kpi-inspection-api',
        project_root='scopes/ada/web/inspection/api',
        ruff_roots=('src', 'tests', 'commented'),
        tests_root='tests',
        source_root='src',
        commented_root='commented',
    ),
    'kpi-inspection-preview': AdaCapability(
        key='kpi-inspection-preview',
        project_root='scopes/ada/web/inspection/preview',
        ruff_roots=('src', 'tests', 'commented'),
        tests_root='tests',
        source_root='src',
        commented_root='commented',
    ),
    'time-status-store-adapter': AdaCapability(
        key='time-status-store-adapter',
        project_root='scopes/ada/web/time-status/store-adapter',
        ruff_roots=('src', 'tests', 'commented'),
        tests_root='tests',
        source_root='src',
        commented_root='commented',
    ),
    'time-status': AdaCapability(
        key='time-status',
        project_root='scopes/ada/web/ui/time-status',
        ruff_roots=('src', 'tests', 'commented'),
        tests_root='tests',
        source_root='src',
        commented_root='commented',
    ),
    'ui-core': AdaCapability(
        key='ui-core',
        project_root='scopes/ada/web/ui/core',
        ruff_roots=('src', 'tests', 'commented'),
        tests_root='tests',
        source_root='src',
        commented_root='commented',
    ),
    'display-status': AdaCapability(
        key='display-status',
        project_root='scopes/ada/web/ui/display-status',
        ruff_roots=('src', 'tests', 'commented'),
        tests_root='tests',
        source_root='src',
        commented_root='commented',
    ),
    # Core y resolver entran al gate agregado recién cuando Generic Application consume el resolver.
    'content-state-core': AdaCapability(
        key='content-state-core',
        project_root='scopes/ada/web/content-state/core',
        ruff_roots=('src', 'tests', 'commented'),
        tests_root='tests',
        source_root='src',
        commented_root='commented',
    ),
    'content-state-dependency-resolver': AdaCapability(
        key='content-state-dependency-resolver',
        project_root='scopes/ada/web/content-state/dependency-resolver',
        ruff_roots=('src', 'tests', 'commented'),
        tests_root='tests',
        source_root='src',
        commented_root='commented',
    ),
    'content-state': AdaCapability(
        key='content-state',
        project_root='scopes/ada/web/ui/content-state',
        ruff_roots=('src', 'tests', 'commented'),
        tests_root='tests',
        source_root='src',
        commented_root='commented',
    ),
    'global-indicator': AdaCapability(
        key='global-indicator',
        project_root='scopes/ada/web/ui/global-indicator',
        ruff_roots=('src', 'tests', 'commented'),
        tests_root='tests',
        source_root='src',
        commented_root='commented',
    ),
    'branding': AdaCapability(
        key='branding',
        project_root='scopes/ada/web/ui/branding',
        ruff_roots=('src', 'tests', 'commented'),
        tests_root='tests',
        source_root='src',
        commented_root='commented',
    ),
    'navigation': AdaCapability(
        key='navigation',
        project_root='scopes/ada/web/shell/navigation',
        ruff_roots=('src', 'tests', 'commented'),
        tests_root='tests',
        source_root='src',
        commented_root='commented',
    ),
    'header': AdaCapability(
        key='header',
        project_root='scopes/ada/web/shell/header',
        ruff_roots=('src', 'tests', 'commented'),
        tests_root='tests',
        source_root='src',
        commented_root='commented',
    ),
    'alarm-management-summary': AdaCapability(
        key='alarm-management-summary',
        project_root='scopes/ada/web/alarms/management-summary',
        ruff_roots=('src', 'tests', 'commented'),
        tests_root='tests',
        source_root='src',
        commented_root='commented',
    ),
    'alarm-status': AdaCapability(
        key='alarm-status',
        project_root='scopes/ada/web/alarms/status',
        ruff_roots=('src', 'tests', 'commented'),
        tests_root='tests',
        source_root='src',
        commented_root='commented',
    ),
    'application': AdaCapability(
        key='application',
        project_root='scopes/ada/web/application/ada-generic-application',
        ruff_roots=('src', 'tests', 'commented'),
        tests_root='tests',
        source_root='src',
        commented_root='commented',
    ),
}


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _run(command: list[str], *, cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Validate ADA scope capabilities by semantic target.',
    )
    parser.add_argument(
        'capabilities',
        nargs='*',
        help='Capabilities to validate. No arguments means all registered ADA capabilities.',
    )
    parser.add_argument('--all', action='store_true', help='Validate all registered capabilities.')
    parser.add_argument(
        '--list', action='store_true', help='List registered capabilities and exit.'
    )
    return parser


def _resolve_capabilities(arguments: argparse.Namespace) -> tuple[AdaCapability, ...]:
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
            f'Unknown ADA capabilities: {", ".join(unknown)}. Valid capabilities: {valid}'
        )

    unique: list[AdaCapability] = []
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


def _validate_capability(capability: AdaCapability, *, root: Path) -> None:
    project = root / capability.project_root
    tooling = (
        root / 'scripts/scopes/ada/check.py',
        root / 'scripts/commented/scopes/ada/check.py',
    )
    ruff_targets = [*capability.ruff_roots, *(str(path) for path in tooling)]

    print(f'ADA capability: {capability.key}')
    print('[1/6] Validating Python runtime')
    _validate_python_version()

    print('[2/6] Applying safe Ruff fixes')
    _run(['ruff', 'check', '--fix', *ruff_targets], cwd=project)

    print('[3/6] Formatting selected ADA capability')
    _run(['ruff', 'format', *ruff_targets], cwd=project)

    print('[4/6] Confirming Ruff-clean state')
    _run(['ruff', 'check', *ruff_targets], cwd=project)
    _run(['ruff', 'format', '--check', *ruff_targets], cwd=project)

    print('[5/6] Running ADA capability tests')
    _run(['pytest', capability.tests_root], cwd=project)

    print('[6/6] Validating productive/commented semantic mirrors')
    validator = root / 'scripts/repository/validate_mirrors.py'
    _run(
        [
            sys.executable,
            str(validator),
            capability.source_root,
            capability.commented_root,
            str(root / 'scripts/scopes/ada'),
            str(root / 'scripts/commented/scopes/ada'),
        ],
        cwd=project,
    )


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    capabilities = _resolve_capabilities(arguments)
    root = _repository_root()

    for capability in capabilities:
        _validate_capability(capability, root=root)

    names = ', '.join(capability.key for capability in capabilities)
    print(f'Atlanticus ADA validated: {names}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
