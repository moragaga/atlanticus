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


class ConsumerProcessError(RuntimeError):
    pass


def _distribution_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (
            (candidate / "distribution.json").is_file()
            and (candidate / "services.json").is_file()
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


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConsumerProcessError(f"JSON file is invalid: {path}") from error


# distribution.json es la autoridad interna de la composición distribuida.
def _manifest(root: Path) -> dict[str, object]:
    path = root / "distribution.json"
    value = _read_json(path)
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != 1
        or not isinstance(value.get("name"), str)
        or not isinstance(value.get("generated_at"), str)
        or not isinstance(value.get("source"), dict)
        or not isinstance(value.get("processes"), list)
    ):
        raise ConsumerProcessError(f"Distribution manifest contract is invalid: {path}")
    source = value["source"]
    if source.get("repository") != "atlanticus" or not isinstance(
        source.get("revision"), str
    ):
        raise ConsumerProcessError(f"Distribution source contract is invalid: {path}")
    return value


# Para ejecución local se usan aliases de deployment, no nombres de source.
def _deployment_entries(root: Path) -> tuple[tuple[str, str], ...]:
    manifest = _manifest(root)
    entries: list[tuple[str, str]] = []
    for item in manifest["processes"]:
        if not isinstance(item, dict):
            raise ConsumerProcessError("Distribution process manifest entry is invalid")
        process = item.get("process")
        deployment = item.get("deployment")
        if (
            not isinstance(process, str)
            or not PROCESS_NAME_PATTERN.fullmatch(process)
            or not isinstance(deployment, dict)
        ):
            raise ConsumerProcessError("Distribution process manifest entry is invalid")
        alias = deployment.get("excecution_file")
        container_name = deployment.get("container_name")
        if (
            not isinstance(alias, str)
            or not PROCESS_NAME_PATTERN.fullmatch(alias)
            or not isinstance(container_name, str)
            or not container_name.startswith("job")
        ):
            raise ConsumerProcessError("Distribution deployment metadata is invalid")
        entries.append((alias, container_name))
    aliases = tuple(alias for alias, _ in entries)
    if len(aliases) != len(set(aliases)):
        raise ConsumerProcessError("Distribution deployment aliases contain duplicates")
    return tuple(entries)


# Reconstruye el contrato esperado del pipeline para detectar drift en services.json.
def _expected_services(root: Path) -> list[dict[str, object]]:
    return [
        {
            "repository": alias,
            "excecution_file": alias,
            "container_name": container_name,
            "config_file": f"processes/{alias}/config.json",
            "to_deploy": True,
            "to_stop": False,
            "to_working_hours_dev": True,
            "to_working_hours_uat": True,
        }
        for alias, container_name in _deployment_entries(root)
    ]


def _compose_file(root: Path, *, bind: bool) -> Path:
    return root / ("compose.bind.yaml" if bind else "compose.yaml")


# Valida coherencia entre manifest, services, carpetas, Compose y configuración local.
def _validate_distribution(root: Path, *, require_environment: bool) -> tuple[str, ...]:
    entries = _deployment_entries(root)
    aliases = tuple(alias for alias, _ in entries)
    process_root = root / "processes"
    actual = tuple(
        sorted(path.name for path in process_root.iterdir() if path.is_dir())
    )
    if actual != tuple(sorted(aliases)):
        raise ConsumerProcessError(
            "Distribution process directories do not match distribution.json"
        )
    for alias in aliases:
        root_for_process = process_root / alias
        for relative in REQUIRED_ARTIFACT_ENTRIES:
            if not (root_for_process / relative).exists():
                raise ConsumerProcessError(
                    f"Process transport artifact is incomplete ({relative}): "
                    f"{root_for_process}"
                )
        if require_environment and not (root_for_process / ".env").is_file():
            raise ConsumerProcessError(
                f"Local process .env file not found: {root_for_process / '.env'}"
            )
    services_path = root / "services.json"
    services = _read_json(services_path)
    if services != _expected_services(root):
        raise ConsumerProcessError(
            f"Pipeline services manifest does not match distribution.json: {services_path}"
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
        for alias in aliases:
            if f"  {alias}:" not in compose or f"FILENAME: {alias}" not in compose:
                raise ConsumerProcessError(
                    f"Distribution Compose is missing deployment alias {alias}: "
                    f"{compose_path}"
                )
    return aliases


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


# El estado bind se crea localmente y nunca viaja dentro de la distribución.
def _ensure_bind_runtime(root: Path) -> None:
    (root / ".runtime/volumen").mkdir(parents=True, exist_ok=True)


def _validate(root: Path) -> None:
    _validate_distribution(root, require_environment=True)


def _build(root: Path, *, bind: bool) -> None:
    _validate_distribution(root, require_environment=True)
    _validate_docker(root)
    if bind:
        _ensure_bind_runtime(root)
    _compose(root, bind=bind, arguments=["down", "--remove-orphans"])
    _compose(root, bind=bind, arguments=["build", "--no-cache"])
    _compose(root, bind=bind, arguments=["config", "--services"])


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


def _run_process(root: Path, *, bind: bool, process: str) -> None:
    aliases = _validate_distribution(root, require_environment=True)
    if process not in aliases:
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
