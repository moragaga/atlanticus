from __future__ import annotations

import argparse
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

# Mantiene el baseline local de ejecución mientras la migración a una versión posterior siga separada.
PYTHON_VERSION = "3.14.2"
BUNDLE_MODULE_NAME = "atlanticus_process_tool_bundle"
LOCAL_MODULE_NAME = "atlanticus_process_tool_local"


# Error operacional de la CLI local; se presenta al usuario sin traceback de infraestructura.
class ProcessToolError(RuntimeError):
    pass


# Resuelve la raíz mediante las dos capacidades Python que esta orquestación compone.
def _repository_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "deployment/processes/bundle.py").is_file() and (
            candidate / "deployment/local/generate_compose.py"
        ).is_file():
            return candidate
    raise ProcessToolError("Atlanticus repository root could not be resolved")


# Carga las capacidades de deployment existentes sin convertirlas en subprocess Python.
def _load_module(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ProcessToolError(f"Python module could not be loaded: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_bundle(repository_root: Path) -> ModuleType:
    return _load_module(
        repository_root / "deployment/processes/bundle.py",
        BUNDLE_MODULE_NAME,
    )


def _load_local(repository_root: Path) -> ModuleType:
    return _load_module(
        repository_root / "deployment/local/generate_compose.py",
        LOCAL_MODULE_NAME,
    )


# Verifica herramientas externas sólo cuando la acción realmente las necesita.
def _require_command(name: str) -> None:
    if shutil.which(name) is None:
        raise ProcessToolError(f"Required command not found: {name}")


# Centraliza subprocess externos y conserva el directorio de trabajo explícito.
def _run(
    command: list[str],
    *,
    cwd: Path,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    print(">", " ".join(command), flush=True)
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            check=True,
            capture_output=capture_output,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ProcessToolError(f"Command failed: {' '.join(command)}") from error


def _workspace_root(repository_root: Path) -> Path:
    return repository_root / ".runtime/local-deployment"


def _compose_file(repository_root: Path) -> Path:
    return _workspace_root(repository_root) / "compose.yaml"


def _compose(
    repository_root: Path,
    *arguments: str,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    return _run(
        [
            "docker",
            "compose",
            "-f",
            str(_compose_file(repository_root)),
            *arguments,
        ],
        cwd=repository_root,
        capture_output=capture_output,
    )


def _require_compose_file(repository_root: Path) -> None:
    compose_file = _compose_file(repository_root)
    if not compose_file.is_file():
        raise ProcessToolError(
            "Local Compose workspace not found. Run the local process tool with: build"
        )


def _validate_docker(repository_root: Path) -> None:
    _require_command("docker")
    _run(["docker", "compose", "version"], cwd=repository_root, capture_output=True)


# Traduce nombres lógicos a layouts de procesos sin mantener inventarios de procesos.
def _target_candidates(repository_root: Path, target: str) -> tuple[Path, ...]:
    candidates = [repository_root / "scopes" / target / "processes"]
    if target.endswith("-backend"):
        scope = target.removesuffix("-backend")
        if scope:
            candidates.append(repository_root / "scopes" / scope / "backend/processes")
    return tuple(dict.fromkeys(path.resolve() for path in candidates))


# Descubre todos los procesos exportables pertenecientes a un target lógico.
def _resolve_target_processes(
    repository_root: Path,
    target: str,
    bundle: ModuleType,
) -> tuple[Path, ...]:
    matches = tuple(
        path for path in _target_candidates(repository_root, target) if path.is_dir()
    )
    if not matches:
        raise ProcessToolError(f"Unknown process target: {target}")
    if len(matches) != 1:
        rendered = ", ".join(str(path) for path in matches)
        raise ProcessToolError(f"Ambiguous process target {target}: {rendered}")
    process_roots: list[Path] = []
    for pyproject_path in sorted(matches[0].glob("*/pyproject.toml")):
        project = bundle.load_project(pyproject_path.parent)
        if not bundle.has_container_contract(project):
            continue
        bundle.load_container_definition(project)
        process_roots.append(pyproject_path.parent)
    if not process_roots:
        raise ProcessToolError(f"No exportable processes found for target: {target}")
    return tuple(process_roots)


# Distingue preparación masiva por target de selección explícita de procesos individuales.
def _resolve_prepare_processes(
    repository_root: Path,
    selections: tuple[str, ...],
    *,
    all_target: bool,
    bundle: ModuleType,
) -> tuple[Path, ...]:
    if all_target:
        if len(selections) != 1:
            raise ProcessToolError("prepare --all requires exactly one process target")
        return _resolve_target_processes(repository_root, selections[0], bundle)
    return tuple(
        bundle.resolve_process_root(repository_root, value) for value in selections
    )


# Reutiliza el contrato local existente: artifact completo, fuente vigente y .env activo.
def _validate_artifacts(repository_root: Path, local: ModuleType):
    definitions = local.discover_processes(repository_root)
    local.validate_artifacts(definitions)
    local.validate_source_contracts(repository_root, definitions)
    local.validate_environment_files(definitions)
    return definitions


# Genera bundles transportables en artifacts/processes sin materializar configuración activa.
def _prepare(
    arguments: argparse.Namespace, repository_root: Path, bundle: ModuleType
) -> None:
    _require_command("uv")
    selections = tuple(arguments.selections)
    process_roots = _resolve_prepare_processes(
        repository_root,
        selections,
        all_target=arguments.all,
        bundle=bundle,
    )
    output_root = repository_root / "artifacts/processes"
    for process_root in process_roots:
        output_path = bundle.build_process_bundle(
            repository_root=repository_root,
            process_root=process_root,
            output_root=output_root,
        )
        print(output_path)
    print(f"Process artifacts prepared in: {output_root}")
    print("Create one .env beside each artifact pyproject.toml before local execution.")


def _validate(repository_root: Path, local: ModuleType) -> None:
    _validate_artifacts(repository_root, local)


# Genera .runtime/local-deployment desde artifacts ya validados.
def _generate_workspace(
    repository_root: Path,
    local: ModuleType,
    *,
    volume_mode: str,
) -> None:
    definitions = _validate_artifacts(repository_root, local)
    compose_path = local.prepare_workspace(
        repository_root=repository_root,
        workspace_root=_workspace_root(repository_root),
        definitions=definitions,
        volume_mode=volume_mode,
    )
    print(compose_path)


# Reconstruye el workspace y las imágenes Docker sin levantar servicios.
def _build(
    arguments: argparse.Namespace,
    repository_root: Path,
    local: ModuleType,
) -> None:
    _validate_docker(repository_root)
    if _compose_file(repository_root).is_file():
        _compose(repository_root, "down", "--remove-orphans")
    _generate_workspace(
        repository_root,
        local,
        volume_mode="bind" if arguments.bind else "named",
    )
    _compose(repository_root, "build", "--no-cache")
    _compose(repository_root, "config", "--services")


# Reconstruye workspace e imágenes y levanta el Compose local.
def _up(
    arguments: argparse.Namespace,
    repository_root: Path,
    local: ModuleType,
) -> None:
    _validate_docker(repository_root)
    if _compose_file(repository_root).is_file():
        _compose(repository_root, "down", "--remove-orphans")
    _generate_workspace(
        repository_root,
        local,
        volume_mode="bind" if arguments.bind else "named",
    )
    _compose(repository_root, "build", "--no-cache")
    _compose(repository_root, "up", "-d")
    _compose(repository_root, "ps", "-a")


def _down(repository_root: Path) -> None:
    _validate_docker(repository_root)
    _require_compose_file(repository_root)
    _compose(repository_root, "down", "--remove-orphans")


def _ps(repository_root: Path) -> None:
    _validate_docker(repository_root)
    _require_compose_file(repository_root)
    _compose(repository_root, "ps", "-a")


def _logs(arguments: argparse.Namespace, repository_root: Path) -> None:
    _validate_docker(repository_root)
    _require_compose_file(repository_root)
    command = ["logs", "-f"]
    if arguments.process is not None:
        command.append(arguments.process)
    _compose(repository_root, *command)


# Ejecuta un único process en modo run-once sólo sobre un workspace vigente.
def _run_process(
    arguments: argparse.Namespace,
    repository_root: Path,
    local: ModuleType,
) -> None:
    _validate_docker(repository_root)
    _validate_artifacts(repository_root, local)
    _require_compose_file(repository_root)
    local.validate_workspace_contract(_workspace_root(repository_root))
    services = _compose(
        repository_root,
        "config",
        "--services",
        capture_output=True,
    ).stdout.splitlines()
    if arguments.process not in services:
        raise ProcessToolError(f"Local Compose service not found: {arguments.process}")
    _compose(repository_root, "run", "--rm", arguments.process, "--run-once")


# Expone targets lógicos en prepare; build/up operan sobre el conjunto de artifacts preparados.
def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare and run Atlanticus process artifacts locally."
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("selections", nargs="+")
    prepare.add_argument(
        "--all",
        action="store_true",
        help="Treat the selection as one logical process target and prepare every process in it.",
    )

    subparsers.add_parser("validate")

    build = subparsers.add_parser("build")
    build.add_argument("--bind", action="store_true")

    up = subparsers.add_parser("up")
    up.add_argument("--bind", action="store_true")

    subparsers.add_parser("down")
    subparsers.add_parser("ps")

    logs = subparsers.add_parser("logs")
    logs.add_argument("process", nargs="?")

    run = subparsers.add_parser("run")
    run.add_argument("process")

    return parser


# Compone bundling, workspace local y Docker bajo una única CLI multiplataforma.
def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    repository_root = _repository_root()
    bundle = _load_bundle(repository_root)
    local = _load_local(repository_root)
    try:
        if arguments.action == "prepare":
            _prepare(arguments, repository_root, bundle)
        elif arguments.action == "validate":
            _validate(repository_root, local)
        elif arguments.action == "build":
            _build(arguments, repository_root, local)
        elif arguments.action == "up":
            _up(arguments, repository_root, local)
        elif arguments.action == "down":
            _down(repository_root)
        elif arguments.action == "ps":
            _ps(repository_root)
        elif arguments.action == "logs":
            _logs(arguments, repository_root)
        elif arguments.action == "run":
            _run_process(arguments, repository_root, local)
        else:
            raise ProcessToolError(f"Unsupported action: {arguments.action}")
    except (
        bundle.ProcessBundleError,
        local.LocalDeploymentError,
        ProcessToolError,
    ) as error:
        raise SystemExit(str(error)) from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
