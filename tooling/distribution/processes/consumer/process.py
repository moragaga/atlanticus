from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

DISTRIBUTION_CONTRACT_KEY = "x-atlanticus-distribution-contract"
DISTRIBUTION_CONTRACT_VERSION = "1"
SIMULATION_MODULE_NAME = "atlanticus_distribution_local_simulation"
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
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    print("> " + " ".join(command), flush=True)
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            check=True,
            capture_output=capture_output,
            text=True,
            env=environment,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ConsumerProcessError(f"Command failed: {' '.join(command)}") from error


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConsumerProcessError(f"JSON file is invalid: {path}") from error


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
        alias = deployment.get("execution_file")
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


def _expected_services(root: Path) -> list[dict[str, object]]:
    return [
        {
            "repository": alias,
            "execution_file": alias,
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
    return root / "deployment/local" / ("compose.bind.yaml" if bind else "compose.yaml")


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
    for compose_path in (
        root / "deployment/local/compose.yaml",
        root / "deployment/local/compose.bind.yaml",
    ):
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
    for required in (
        root / "deployment/local/simulation.py",
        root / "deployment/local/scheduler/Dockerfile",
        root / "deployment/local/scheduler/scheduler.py",
    ):
        if not required.is_file():
            raise ConsumerProcessError(
                f"Distribution local deployment capability is missing: {required}"
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
    compose_file: Path | None = None,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    selected_compose = (
        _compose_file(root, bind=bind) if compose_file is None else compose_file
    )
    return _run(
        [
            "docker",
            "compose",
            "-f",
            str(selected_compose),
            *arguments,
        ],
        cwd=root,
        capture_output=capture_output,
        environment=environment,
    )


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


def _load_simulation(root: Path):
    path = root / "deployment/local/simulation.py"
    spec = importlib.util.spec_from_file_location(SIMULATION_MODULE_NAME, path)
    if spec is None or spec.loader is None:
        raise ConsumerProcessError(
            f"Local simulation module could not be loaded: {path}"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _docker_value(root: Path, *arguments: str) -> str:
    return _run(
        ["docker", *arguments],
        cwd=root,
        capture_output=True,
    ).stdout.strip()


def _simulation_environment(root: Path, simulation) -> dict[str, str]:
    endpoint = _docker_value(
        root,
        "context",
        "inspect",
        "--format",
        "{{.Endpoints.docker.Host}}",
    )
    operating_system = _docker_value(
        root,
        "info",
        "--format",
        "{{.OperatingSystem}}",
    )
    engine_type = _docker_value(
        root,
        "info",
        "--format",
        "{{.OSType}}",
    )
    environment = os.environ.copy()
    environment["ATLANTICUS_DOCKER_SOCKET_SOURCE"] = (
        simulation.resolve_docker_socket_source(
            endpoint=endpoint,
            operating_system=operating_system,
            engine_type=engine_type,
        )
    )
    return environment


def _simulation_compose_files(root: Path) -> tuple[Path, ...]:
    local_root = root / "deployment/local"
    return (
        local_root / "compose.simulate.yaml",
        local_root / "compose.simulate.bind.yaml",
    )


def _simulation_processes(root: Path, simulation) -> tuple[object, ...]:
    manifest = _manifest(root)
    distribution_name = manifest["name"]
    return tuple(
        simulation.load_simulation_process(
            process_root=root / "processes" / alias,
            name=alias,
            image=f"atlanticus-{distribution_name}-{alias}:local",
        )
        for alias, _ in _deployment_entries(root)
    )


def _prepare_simulation(root: Path, simulation, *, bind: bool) -> Path:
    manifest = _manifest(root)
    distribution_name = manifest["name"]
    local_root = root / "deployment/local"
    if bind:
        _ensure_bind_runtime(root)
    return simulation.prepare_simulation(
        workspace_root=root,
        local_root=local_root,
        scheduler_source=local_root / "scheduler",
        project_name=f"atlanticus-{distribution_name}-local",
        simulation_name=distribution_name,
        processes=_simulation_processes(root, simulation),
        volume_mode="bind" if bind else "named",
        bind_runtime=root / ".runtime/volumen",
    )


def _cleanup_simulation_containers(root: Path, simulation_name: str) -> None:
    for role in ("scheduler", "execution"):
        completed = _run(
            [
                "docker",
                "ps",
                "-aq",
                "--filter",
                f"label=atlanticus.simulation={simulation_name}",
                "--filter",
                f"label=atlanticus.role={role}",
            ],
            cwd=root,
            capture_output=True,
        )
        ids = tuple(line for line in completed.stdout.splitlines() if line)
        if ids:
            _run(["docker", "rm", "-f", *ids], cwd=root)


def _simulate(root: Path, simulation, *, bind: bool) -> None:
    _validate_distribution(root, require_environment=True)
    _validate_docker(root)
    compose_path = _prepare_simulation(root, simulation, bind=bind)
    _compose(root, bind=bind, arguments=["build", "--no-cache"])
    environment = _simulation_environment(root, simulation)
    distribution_name = _manifest(root)["name"]
    _cleanup_simulation_containers(root, distribution_name)
    _compose(
        root,
        bind=bind,
        arguments=["build", "--no-cache", "scheduler"],
        compose_file=compose_path,
        environment=environment,
    )
    _compose(
        root,
        bind=bind,
        arguments=[
            "run",
            "--rm",
            "--entrypoint",
            "docker",
            "scheduler",
            "version",
        ],
        compose_file=compose_path,
        environment=environment,
    )
    _compose(
        root,
        bind=bind,
        arguments=["up", "-d", "scheduler"],
        compose_file=compose_path,
        environment=environment,
    )
    _compose(
        root,
        bind=bind,
        arguments=["ps", "-a"],
        compose_file=compose_path,
        environment=environment,
    )


def _simulate_stop(root: Path, simulation) -> None:
    _validate_docker(root)
    environment = _simulation_environment(root, simulation)
    distribution_name = _manifest(root)["name"]
    _cleanup_simulation_containers(root, distribution_name)
    for compose_path in _simulation_compose_files(root):
        if not compose_path.is_file():
            continue
        _compose(
            root,
            bind=compose_path.name.endswith(".bind.yaml"),
            arguments=["down", "--remove-orphans"],
            compose_file=compose_path,
            environment=environment,
        )


def _add_bind_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--bind", action="store_true")


def _extension_manifest(archive: zipfile.ZipFile) -> dict[str, object]:
    try:
        value = json.loads(archive.read("extension.json"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ConsumerProcessError(
            "Extension manifest is missing or invalid"
        ) from error
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != 1
        or not isinstance(value.get("name"), str)
        or not PROCESS_NAME_PATTERN.fullmatch(value["name"])
        or not isinstance(value.get("generated_at"), str)
        or not isinstance(value.get("source"), dict)
        or not isinstance(value.get("processes"), list)
        or not value["processes"]
    ):
        raise ConsumerProcessError("Extension manifest contract is invalid")
    source = value["source"]
    if source.get("repository") != "atlanticus" or not re.fullmatch(
        r"[0-9a-f]{40}", str(source.get("revision", ""))
    ):
        raise ConsumerProcessError("Extension source contract is invalid")
    for process in value["processes"]:
        if not isinstance(process, dict) or not isinstance(
            process.get("deployment"), dict
        ):
            raise ConsumerProcessError("Extension process entry is invalid")
        deployment = process["deployment"]
        runtime = process.get("runtime")
        for candidate in (process.get("process"), deployment.get("execution_file")):
            if not isinstance(candidate, str) or not PROCESS_NAME_PATTERN.fullmatch(
                candidate
            ):
                raise ConsumerProcessError("Extension process identity is invalid")
        if (
            not isinstance(process.get("project"), str)
            or not isinstance(process.get("version"), str)
            or not isinstance(process.get("description"), str)
            or not isinstance(deployment.get("container_name"), str)
            or not re.fullmatch(r"job[0-9]+", deployment["container_name"])
            or not isinstance(runtime, dict)
            or runtime.get("language") != "python"
            or not isinstance(runtime.get("version"), str)
        ):
            raise ConsumerProcessError("Extension process metadata is invalid")
        if "source" in process and process["source"] != source:
            raise ConsumerProcessError(
                "Extension process source does not match its package"
            )
    return value


def _validate_extension_archive(
    archive: zipfile.ZipFile,
    extension: dict[str, object],
) -> None:
    aliases = {item["deployment"]["execution_file"] for item in extension["processes"]}
    if len(aliases) != len(extension["processes"]):
        raise ConsumerProcessError("Extension deployment aliases contain duplicates")
    if len({item["process"] for item in extension["processes"]}) != len(aliases):
        raise ConsumerProcessError("Extension process commands contain duplicates")
    if len(
        {item["deployment"]["container_name"] for item in extension["processes"]}
    ) != len(aliases):
        raise ConsumerProcessError("Extension container names contain duplicates")
    names: set[str] = set()
    total_size = 0
    members = archive.infolist()
    if len(members) > 10000:
        raise ConsumerProcessError("Extension archive has too many entries")
    for member in members:
        raw = member.filename
        normalized = raw.rstrip("/")
        parts = normalized.split("/")
        mode = (member.external_attr >> 16) & 0xFFFF
        if (
            not raw
            or "\\" in raw
            or raw.startswith("/")
            or any(part in {"", ".", ".."} for part in parts)
            or normalized in names
            or stat.S_ISLNK(mode)
        ):
            raise ConsumerProcessError(f"Unsafe extension archive entry: {raw}")
        names.add(normalized)
        if normalized == "extension.json" and not member.is_dir():
            continue
        if normalized == "processes" and member.is_dir():
            continue
        if len(parts) < 2 or parts[0] != "processes":
            raise ConsumerProcessError(f"Unexpected extension archive entry: {raw}")
        if len(parts) == 2:
            if parts[1] not in aliases or not member.is_dir():
                raise ConsumerProcessError(f"Unexpected extension directory: {raw}")
            continue
        if parts[1] not in aliases:
            raise ConsumerProcessError(f"Unexpected extension process: {raw}")
        if len(parts) >= 3 and any(
            part in {".env", "config.json", "secrets.json"}
            or (part.startswith(".env.") and part != ".env.detail")
            for part in parts[2:]
        ):
            raise ConsumerProcessError(
                f"Active configuration must not be packaged: {raw}"
            )
        total_size += member.file_size
        if total_size > 2_000_000_000:
            raise ConsumerProcessError("Extension archive is too large")
    if "extension.json" not in names:
        raise ConsumerProcessError("Extension manifest is missing")
    for alias in aliases:
        for relative in (
            *REQUIRED_ARTIFACT_ENTRIES,
            ".env.detail",
            "config.detail.json",
            "secrets.detail.json",
        ):
            if f"processes/{alias}/{relative}" not in names:
                raise ConsumerProcessError(
                    f"Extension process artifact is incomplete ({relative}): {alias}"
                )
    if archive.testzip() is not None:
        raise ConsumerProcessError("Extension archive checksum validation failed")


def _read_process_contract(root: Path, process: dict[str, object]) -> tuple[float, str]:
    alias = process["deployment"]["execution_file"]
    path = root / "processes" / alias / "pyproject.toml"
    try:
        with path.open("rb") as stream:
            metadata = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConsumerProcessError(
            f"Extension project metadata is invalid: {path}"
        ) from error
    project = metadata.get("project")
    tool = metadata.get("tool")
    atlanticus = tool.get("atlanticus") if isinstance(tool, dict) else None
    container = atlanticus.get("container") if isinstance(atlanticus, dict) else None
    if (
        not isinstance(project, dict)
        or not isinstance(container, dict)
        or project.get("name") != process["project"]
        or project.get("version") != process["version"]
        or project.get("requires-python") != f"=={process['runtime']['version']}"
        or container.get("command") != process["process"]
        or container.get("system-profile") not in {"base", "sqlserver"}
        or not isinstance(project.get("scripts"), dict)
        or process["process"] not in project["scripts"]
    ):
        raise ConsumerProcessError(
            f"Extension project contract does not match manifest: {alias}"
        )
    resources = container.get("resources", {})
    cpus = resources.get("cpus", 0.5) if isinstance(resources, dict) else None
    memory = resources.get("memory", "1g") if isinstance(resources, dict) else None
    if (
        isinstance(cpus, bool)
        or not isinstance(cpus, (int, float))
        or cpus <= 0
        or not isinstance(memory, str)
        or not re.fullmatch(r"[1-9][0-9]*(?:\.[0-9]+)?[bkmg]?", memory, re.IGNORECASE)
    ):
        raise ConsumerProcessError(f"Extension process resources are invalid: {alias}")
    return float(cpus), memory.lower()


def _render_extension_compose(root: Path, *, volume_mode: str) -> str:
    manifest = _manifest(root)
    distribution_name = manifest["name"]
    volume_source = "runtime" if volume_mode == "named" else "../../.runtime/volumen"
    services = []
    for process in manifest["processes"]:
        alias = process["deployment"]["execution_file"]
        cpus, memory = _read_process_contract(root, process)
        services.append(
            "\n".join(
                (
                    f"  {alias}:",
                    f"    image: atlanticus-{distribution_name}-{alias}:local",
                    "    build:",
                    "      context: ../..",
                    "      dockerfile: Dockerfile",
                    "      args:",
                    f"        FILENAME: {alias}",
                    '    command: ["--run-once"]',
                    '    restart: "no"',
                    "    env_file:",
                    f"      - ../../processes/{alias}/.env",
                    "    environment:",
                    "      VOLUMEN_PATH: /app/volumen",
                    "    volumes:",
                    f"      - {volume_source}:/app/volumen",
                    f"    cpus: {cpus:g}",
                    f"    mem_limit: {memory}",
                )
            )
        )
    volumes = "\nvolumes:\n  runtime:\n" if volume_mode == "named" else ""
    return (
        f"name: atlanticus-{distribution_name}-local\n"
        f'{DISTRIBUTION_CONTRACT_KEY}: "{DISTRIBUTION_CONTRACT_VERSION}"\n'
        f"services:\n{'\n'.join(services)}\n{volumes}"
    )


def _integrate(root: Path, extension_path: Path) -> None:
    _validate_distribution(root, require_environment=False)
    previous = _manifest(root)
    installed = _deployment_entries(root)
    used_aliases = {alias for alias, _ in installed}
    used_containers = {container for _, container in installed}
    used_commands = {item["process"] for item in previous["processes"]}
    extension_path = extension_path.resolve()
    try:
        with zipfile.ZipFile(extension_path) as archive:
            extension = _extension_manifest(archive)
            _validate_extension_archive(archive, extension)
            additions = extension["processes"]
            versions = {
                item["runtime"]["version"]
                for item in (*previous["processes"], *additions)
            }
            if len(versions) != 1:
                raise ConsumerProcessError(
                    "Extension Python runtime differs from the distribution"
                )
            for item in additions:
                deployment = item["deployment"]
                if (
                    item["process"] in used_commands
                    or deployment["execution_file"] in used_aliases
                    or deployment["container_name"] in used_containers
                ):
                    raise ConsumerProcessError(
                        f"Extension conflicts with an installed process: {item['process']}"
                    )
            if (root / "processes").is_symlink():
                raise ConsumerProcessError(
                    "Distribution processes directory cannot be a symlink"
                )
            temporary = Path(
                tempfile.mkdtemp(prefix=f".{root.name}-integrate-", dir=root.parent)
            )
            try:
                candidate = temporary / root.name
                shutil.copytree(
                    root,
                    candidate,
                    symlinks=True,
                    ignore=shutil.ignore_patterns(".runtime"),
                )
                for member in archive.infolist():
                    if member.filename == "extension.json":
                        continue
                    destination = candidate.joinpath(
                        *member.filename.rstrip("/").split("/")
                    )
                    if member.is_dir():
                        destination.mkdir(parents=True, exist_ok=True)
                        continue
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with (
                        archive.open(member) as source,
                        destination.open("xb") as target,
                    ):
                        shutil.copyfileobj(source, target)
                for item in additions:
                    _read_process_contract(candidate, item)
                merged = dict(previous)
                merged["processes"] = [
                    *previous["processes"],
                    *({**item, "source": extension["source"]} for item in additions),
                ]
                (candidate / "distribution.json").write_text(
                    json.dumps(merged, indent=2) + "\n", encoding="utf-8"
                )
                (candidate / "services.json").write_text(
                    json.dumps(_expected_services(candidate), indent=2) + "\n",
                    encoding="utf-8",
                )
                local = candidate / "deployment/local"
                for name, mode in (
                    ("compose.yaml", "named"),
                    ("compose.bind.yaml", "bind"),
                ):
                    (local / name).write_text(
                        _render_extension_compose(candidate, volume_mode=mode),
                        encoding="utf-8",
                    )
                _validate_distribution(candidate, require_environment=False)
                managed = (
                    "distribution.json",
                    "services.json",
                    "deployment/local/compose.yaml",
                    "deployment/local/compose.bind.yaml",
                )
                backup = temporary / "backup"
                for relative in managed:
                    original = root / relative
                    previous_file = backup / relative
                    previous_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(original, previous_file)
                created: list[Path] = []
                published: list[str] = []
                try:
                    for item in additions:
                        alias = item["deployment"]["execution_file"]
                        destination = root / "processes" / alias
                        os.replace(candidate / "processes" / alias, destination)
                        created.append(destination)
                    for relative in managed:
                        os.replace(candidate / relative, root / relative)
                        published.append(relative)
                except BaseException:
                    for relative in reversed(published):
                        os.replace(backup / relative, root / relative)
                    for destination in reversed(created):
                        shutil.rmtree(destination)
                    raise
            finally:
                shutil.rmtree(temporary, ignore_errors=True)
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        if isinstance(error, ConsumerProcessError):
            raise
        raise ConsumerProcessError(
            f"Extension integration failed: {extension_path}"
        ) from error
    print(f"Integrated extension: {extension_path}")
    print("Configure new process .env, config.json and secrets.json before validation.")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and run one Atlanticus process distribution locally."
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    subparsers.add_parser("validate")
    integrate = subparsers.add_parser("integrate")
    integrate.add_argument("extension", type=Path)

    build = subparsers.add_parser("build")
    _add_bind_argument(build)

    up = subparsers.add_parser("up")
    _add_bind_argument(up)

    simulate = subparsers.add_parser("simulate")
    _add_bind_argument(simulate)

    subparsers.add_parser("simulate-stop")

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
    simulation = _load_simulation(root)
    try:
        if arguments.action == "validate":
            _validate(root)
        elif arguments.action == "integrate":
            _integrate(root, arguments.extension)
        elif arguments.action == "build":
            _build(root, bind=arguments.bind)
        elif arguments.action == "up":
            _up(root, bind=arguments.bind)
        elif arguments.action == "simulate":
            _simulate(root, simulation, bind=arguments.bind)
        elif arguments.action == "simulate-stop":
            _simulate_stop(root, simulation)
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
    except (ConsumerProcessError, simulation.LocalSimulationError) as error:
        raise SystemExit(str(error)) from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
