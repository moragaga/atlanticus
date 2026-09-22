from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path

DISTRIBUTION_CONTRACT_KEY = "x-atlanticus-distribution-contract"
DISTRIBUTION_CONTRACT_VERSION = "1"
PROCESS_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REQUIRED_ARTIFACT_ENTRIES = ("pyproject.toml", "uv.lock", "wheels", "src")


# Error operacional del runner que viaja con la distribución.
class ConsumerProcessError(RuntimeError):
    pass


# Resuelve la raíz autónoma sin depender del repository source de Atlanticus.
def _distribution_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (
            (candidate / "distribution.json").is_file()
            and (candidate / "Dockerfile").is_file()
            and (candidate / "processes").is_dir()
        ):
            return candidate
    raise ConsumerProcessError("Atlanticus distribution root could not be resolved")


def _require_command(name: str) -> None:
    if shutil.which(name) is None:
        raise ConsumerProcessError(f"Required command not found: {name}")


def _run(
    command: list[str],
    *,
    cwd: Path,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    print("> " + " ".join(command), flush=True)
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            check=True,
            capture_output=capture_output,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ConsumerProcessError(f"Command failed: {' '.join(command)}") from error


def _manifest(root: Path) -> dict[str, object]:
    path = root / "distribution.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConsumerProcessError(
            f"Distribution manifest is invalid: {path}"
        ) from error
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != 1
        or not isinstance(value.get("name"), str)
        or not isinstance(value.get("processes"), list)
    ):
        raise ConsumerProcessError(f"Distribution manifest contract is invalid: {path}")
    return value


def _process_names(root: Path) -> tuple[str, ...]:
    manifest = _manifest(root)
    names: list[str] = []
    for item in manifest["processes"]:
        if not isinstance(item, dict):
            raise ConsumerProcessError("Distribution process manifest entry is invalid")
        name = item.get("name")
        if not isinstance(name, str) or not PROCESS_NAME_PATTERN.fullmatch(name):
            raise ConsumerProcessError("Distribution process name is invalid")
        names.append(name)
    if len(names) != len(set(names)):
        raise ConsumerProcessError("Distribution process manifest contains duplicates")
    return tuple(names)


def _compose_file(root: Path, *, bind: bool) -> Path:
    return root / ("compose.bind.yaml" if bind else "compose.yaml")


def _validate_distribution(root: Path, *, require_environment: bool) -> tuple[str, ...]:
    names = _process_names(root)
    process_root = root / "processes"
    actual = tuple(
        sorted(path.name for path in process_root.iterdir() if path.is_dir())
    )
    if actual != tuple(sorted(names)):
        raise ConsumerProcessError(
            "Distribution process directories do not match distribution.json"
        )
    for name in names:
        root_for_process = process_root / name
        for relative in REQUIRED_ARTIFACT_ENTRIES:
            if not (root_for_process / relative).exists():
                raise ConsumerProcessError(
                    f"Process transport artifact is incomplete ({relative}): {root_for_process}"
                )
        if require_environment and not (root_for_process / ".env").is_file():
            raise ConsumerProcessError(
                f"Local process .env file not found: {root_for_process / '.env'}"
            )
    marker = f'{DISTRIBUTION_CONTRACT_KEY}: "{DISTRIBUTION_CONTRACT_VERSION}"'
    for compose_path in (root / "compose.yaml", root / "compose.bind.yaml"):
        if not compose_path.is_file():
            raise ConsumerProcessError(
                f"Distribution Compose file not found: {compose_path}"
            )
        compose = compose_path.read_text(encoding="utf-8")
        if marker not in compose:
            raise ConsumerProcessError(
                f"Distribution Compose contract is unsupported: {compose_path}"
            )
        for name in names:
            if f"  {name}:" not in compose:
                raise ConsumerProcessError(
                    f"Distribution Compose is missing process {name}: {compose_path}"
                )
    return names


# Docker sólo se exige para acciones que realmente interactúan con el runtime.
def _validate_docker(root: Path) -> None:
    _require_command("docker")
    _run(["docker", "compose", "version"], cwd=root, capture_output=True)


def _compose(
    root: Path,
    *,
    bind: bool,
    arguments: list[str],
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    return _run(
        [
            "docker",
            "compose",
            "-f",
            str(_compose_file(root, bind=bind)),
            *arguments,
        ],
        cwd=root,
        capture_output=capture_output,
    )


# El volumen bind se materializa como estado local y nunca forma parte del paquete distribuido.
def _ensure_bind_runtime(root: Path) -> None:
    (root / ".runtime/volumen").mkdir(parents=True, exist_ok=True)


def _validate(root: Path) -> None:
    _validate_distribution(root, require_environment=True)


# Construye imágenes sin levantar servicios.
def _build(root: Path, *, bind: bool) -> None:
    _validate_distribution(root, require_environment=True)
    _validate_docker(root)
    if bind:
        _ensure_bind_runtime(root)
    _compose(root, bind=bind, arguments=["down", "--remove-orphans"])
    _compose(root, bind=bind, arguments=["build", "--no-cache"])
    _compose(root, bind=bind, arguments=["config", "--services"])


# Reconstruye imágenes y levanta la composición seleccionada.
def _up(root: Path, *, bind: bool) -> None:
    _validate_distribution(root, require_environment=True)
    _validate_docker(root)
    if bind:
        _ensure_bind_runtime(root)
    _compose(root, bind=bind, arguments=["down", "--remove-orphans"])
    _compose(root, bind=bind, arguments=["build", "--no-cache"])
    _compose(root, bind=bind, arguments=["up", "-d"])
    _compose(root, bind=bind, arguments=["ps", "-a"])


def _down(root: Path, *, bind: bool) -> None:
    _validate_docker(root)
    _compose(root, bind=bind, arguments=["down", "--remove-orphans"])


def _ps(root: Path, *, bind: bool) -> None:
    _validate_docker(root)
    _compose(root, bind=bind, arguments=["ps", "-a"])


def _logs(root: Path, *, bind: bool, process: str | None) -> None:
    _validate_docker(root)
    command = ["logs", "-f"]
    if process is not None:
        command.append(process)
    _compose(root, bind=bind, arguments=command)


# Ejecuta un único proceso run-once dentro del mismo contrato distribuido.
def _run_process(root: Path, *, bind: bool, process: str) -> None:
    names = _validate_distribution(root, require_environment=True)
    if process not in names:
        raise ConsumerProcessError(f"Distribution process not found: {process}")
    _validate_docker(root)
    if bind:
        _ensure_bind_runtime(root)
    services = _compose(
        root,
        bind=bind,
        arguments=["config", "--services"],
        capture_output=True,
    ).stdout.splitlines()
    if process not in services:
        raise ConsumerProcessError(f"Compose service not found: {process}")
    _compose(
        root,
        bind=bind,
        arguments=["run", "--rm", process, "--run-once"],
    )


def _add_bind_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--bind", action="store_true")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and run one Atlanticus process distribution locally."
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    subparsers.add_parser("validate")

    build = subparsers.add_parser("build")
    _add_bind_argument(build)

    up = subparsers.add_parser("up")
    _add_bind_argument(up)

    down = subparsers.add_parser("down")
    _add_bind_argument(down)

    ps = subparsers.add_parser("ps")
    _add_bind_argument(ps)

    logs = subparsers.add_parser("logs")
    logs.add_argument("process", nargs="?")
    _add_bind_argument(logs)

    run = subparsers.add_parser("run")
    run.add_argument("process")
    _add_bind_argument(run)

    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    root = _distribution_root()
    try:
        if arguments.action == "validate":
            _validate(root)
        elif arguments.action == "build":
            _build(root, bind=arguments.bind)
        elif arguments.action == "up":
            _up(root, bind=arguments.bind)
        elif arguments.action == "down":
            _down(root, bind=arguments.bind)
        elif arguments.action == "ps":
            _ps(root, bind=arguments.bind)
        elif arguments.action == "logs":
            _logs(
                root,
                bind=arguments.bind,
                process=arguments.process,
            )
        elif arguments.action == "run":
            _run_process(
                root,
                bind=arguments.bind,
                process=arguments.process,
            )
        else:
            raise ConsumerProcessError(f"Unsupported action: {arguments.action}")
    except ConsumerProcessError as error:
        raise SystemExit(str(error)) from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
