from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

# Runtime Python autorizado para los gates de Atlanticus.
EXPECTED_PYTHON_VERSION = '3.14.2'


@dataclass(frozen=True, slots=True)
class WebCapability:
    # Identificador semántico usado en la línea de comandos.
    key: str
    # Raíz física del paquete dentro de web/.
    package_root: str
    # Suite de pruebas autoritativa de la capability.
    tests_root: str
    # Fuente productiva que debe tener espejo comentado equivalente.
    source_root: str
    # Espejo comentado correspondiente.
    commented_root: str


# El registro desacopla los comandos de mantenimiento de las rutas físicas.
# Agregar una capability Web nueva requiere registrarla aquí, no crear otro script.
CAPABILITIES: dict[str, WebCapability] = {
    'core': WebCapability(
        key='core',
        package_root='framework/core',
        tests_root='framework/core/tests',
        source_root='framework/core/src',
        commented_root='framework/core/commented',
    ),
    'observability': WebCapability(
        key='observability',
        package_root='framework/observability',
        tests_root='framework/observability/tests',
        source_root='framework/observability/src',
        commented_root='framework/observability/commented',
    ),
}


def _repository_root() -> Path:
    # scripts/web/check.py está dos niveles bajo la raíz del repositorio.
    return Path(__file__).resolve().parents[2]


def _web_root() -> Path:
    return _repository_root() / 'web'


def _run(command: list[str], *, cwd: Path) -> None:
    # Todos los subprocesos fallan inmediatamente si el comando retorna error.
    subprocess.run(command, cwd=cwd, check=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Validate Atlanticus Web capabilities by semantic target.',
    )
    parser.add_argument(
        'capabilities',
        nargs='*',
        help='Capabilities to validate. No arguments means all registered Web capabilities.',
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Validate all registered Web capabilities.',
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List registered Web capabilities and exit.',
    )
    return parser


def _resolve_capabilities(arguments: argparse.Namespace) -> tuple[WebCapability, ...]:
    # --list permite descubrir la interfaz semántica sin conocer el tree interno.
    if arguments.list:
        for key in CAPABILITIES:
            print(key)
        raise SystemExit(0)

    requested = list(arguments.capabilities)
    if arguments.all and requested:
        raise SystemExit('Use --all or explicit capabilities, not both')

    # Sin argumentos se interpreta como el gate completo de la frontera Web.
    if arguments.all or not requested:
        requested = list(CAPABILITIES)

    unknown = [key for key in requested if key not in CAPABILITIES]
    if unknown:
        valid = ', '.join(CAPABILITIES)
        joined = ', '.join(unknown)
        raise SystemExit(f'Unknown Web capabilities: {joined}. Valid capabilities: {valid}')

    # Se conserva el orden solicitado y se eliminan duplicados.
    unique: list[WebCapability] = []
    seen: set[str] = set()
    for key in requested:
        if key not in seen:
            unique.append(CAPABILITIES[key])
            seen.add(key)
    return tuple(unique)


def _tooling_python_paths(root: Path) -> tuple[str, ...]:
    # El propio tooling Web también se normaliza con Ruff durante cada gate.
    paths = (
        root / 'scripts/web/check.py',
        root / 'scripts/repository/validate_mirrors.py',
        root / 'scripts/commented/web/check.py',
        root / 'scripts/commented/repository/validate_mirrors.py',
    )
    return tuple(str(path) for path in paths)


def _validate_python_version() -> None:
    version = platform.python_version()
    if version != EXPECTED_PYTHON_VERSION:
        raise SystemExit(f'Expected Python {EXPECTED_PYTHON_VERSION}, found {version}')


def _validate_mirrors(
    capabilities: tuple[WebCapability, ...],
    *,
    root: Path,
    web: Path,
) -> None:
    validator = root / 'scripts/repository/validate_mirrors.py'
    arguments = [sys.executable, str(validator)]
    # Se agregan únicamente los pares de las capabilities seleccionadas.
    for capability in capabilities:
        arguments.extend(
            (
                capability.source_root,
                capability.commented_root,
            )
        )
    # El tooling nuevo mantiene también su espejo comentado.
    arguments.extend(
        (
            str(root / 'scripts/web'),
            str(root / 'scripts/commented/web'),
            str(root / 'scripts/repository'),
            str(root / 'scripts/commented/repository'),
        )
    )
    _run(arguments, cwd=web)


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    capabilities = _resolve_capabilities(arguments)

    root = _repository_root()
    web = _web_root()
    package_roots = [capability.package_root for capability in capabilities]
    tests = [capability.tests_root for capability in capabilities]
    ruff_targets = [*package_roots, *_tooling_python_paths(root)]
    names = ', '.join(capability.key for capability in capabilities)

    print(f'Atlanticus Web capabilities: {names}')

    print('[1/6] Validating Python runtime')
    _validate_python_version()

    print('[2/6] Applying safe Ruff fixes')
    _run(['ruff', 'check', '--fix', *ruff_targets], cwd=web)

    print('[3/6] Formatting selected Web capabilities')
    _run(['ruff', 'format', *ruff_targets], cwd=web)

    print('[4/6] Confirming Ruff-clean state')
    _run(['ruff', 'check', *ruff_targets], cwd=web)
    _run(['ruff', 'format', '--check', *ruff_targets], cwd=web)

    print('[5/6] Running selected Web tests')
    _run(['pytest', *tests], cwd=web)

    print('[6/6] Validating productive/commented semantic mirrors')
    _validate_mirrors(capabilities, root=root, web=web)

    print(f'Atlanticus Web validated: {names}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
