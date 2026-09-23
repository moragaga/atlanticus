from __future__ import annotations

import json
import os
import re
import shutil
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CPUS = 0.5
DEFAULT_MEMORY = "1g"
DOCKER_SOCKET_TARGET = "/var/run/docker.sock"
DOCKER_DESKTOP_SOCKET_SOURCE = "/var/run/docker.sock.raw"
RUNTIME_TARGET = "/app/volumen"
WORKSPACE_TARGET = "/workspace"
PROCESS_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


# Error de contrato o preparación de la simulación local.
class LocalSimulationError(RuntimeError):
    pass


# Contrato inmutable usado para describir un proceso simulable.
@dataclass(frozen=True, slots=True)
class SimulationProcess:
    name: str
    image: str
    env_file: Path
    config_file: Path
    cpus: float
    memory: str


# Normaliza la conexión al Engine sin depender de rutas del usuario.
def resolve_docker_socket_source(
    *,
    endpoint: str,
    operating_system: str,
    engine_type: str,
) -> str:
    if engine_type.strip().lower() != "linux":
        raise LocalSimulationError(
            f"Local simulation requires a Linux Docker engine, found: {engine_type}"
        )
    normalized_endpoint = endpoint.strip()
    normalized_operating_system = operating_system.strip().lower()
    if "docker desktop" in normalized_operating_system:
        return DOCKER_DESKTOP_SOCKET_SOURCE
    if normalized_endpoint.startswith("npipe://"):
        return DOCKER_DESKTOP_SOCKET_SOURCE
    if normalized_endpoint.startswith("unix://"):
        path = normalized_endpoint.removeprefix("unix://")
        if not path:
            raise LocalSimulationError("Docker Unix socket endpoint is empty")
        return path
    raise LocalSimulationError(
        f"Unsupported Docker endpoint for local simulation: {normalized_endpoint}"
    )


# Lee recursos y configuración activa desde el proceso preparado.
def load_simulation_process(
    *,
    process_root: Path,
    name: str,
    image: str,
) -> SimulationProcess:
    if PROCESS_NAME_PATTERN.fullmatch(name) is None:
        raise LocalSimulationError(f"Invalid simulation process name: {name}")
    pyproject_path = process_root / "pyproject.toml"
    try:
        metadata = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise LocalSimulationError(
            f"Could not read process metadata: {pyproject_path}"
        ) from error
    tool = metadata.get("tool")
    atlanticus = tool.get("atlanticus") if isinstance(tool, dict) else None
    container = atlanticus.get("container") if isinstance(atlanticus, dict) else None
    if not isinstance(container, dict):
        raise LocalSimulationError(f"Container metadata is missing: {pyproject_path}")
    resources = container.get("resources", {})
    if not isinstance(resources, dict):
        raise LocalSimulationError(f"Container resources are invalid: {pyproject_path}")
    cpus = resources.get("cpus", DEFAULT_CPUS)
    memory = resources.get("memory", DEFAULT_MEMORY)
    if isinstance(cpus, bool) or not isinstance(cpus, (int, float)) or cpus <= 0:
        raise LocalSimulationError(
            f"Container cpus must be greater than zero: {pyproject_path}"
        )
    if not isinstance(memory, str) or not memory.strip():
        raise LocalSimulationError(f"Container memory is invalid: {pyproject_path}")
    env_file = process_root / ".env"
    config_file = process_root / "config.json"
    if not env_file.is_file():
        raise LocalSimulationError(f"Simulation .env file not found: {env_file}")
    if not config_file.is_file():
        raise LocalSimulationError(f"Simulation config file not found: {config_file}")
    return SimulationProcess(
        name=name,
        image=image,
        env_file=env_file,
        config_file=config_file,
        cpus=float(cpus),
        memory=memory.strip().lower(),
    )


# Materializa spec y Compose de simulación sin ejecutar Docker.
def prepare_simulation(
    *,
    workspace_root: Path,
    local_root: Path,
    scheduler_source: Path,
    project_name: str,
    simulation_name: str,
    processes: tuple[SimulationProcess, ...],
    volume_mode: str,
    bind_runtime: Path,
) -> Path:
    if not processes:
        raise LocalSimulationError("At least one process is required for simulation")
    if volume_mode not in {"named", "bind"}:
        raise LocalSimulationError(f"Unsupported simulation volume mode: {volume_mode}")
    if PROCESS_NAME_PATTERN.fullmatch(simulation_name) is None:
        raise LocalSimulationError(f"Invalid simulation name: {simulation_name}")
    workspace_root = workspace_root.resolve()
    local_root = local_root.resolve()
    local_root.mkdir(parents=True, exist_ok=True)
    scheduler_target = local_root / "scheduler"
    if scheduler_source.resolve() != scheduler_target:
        if scheduler_target.exists():
            shutil.rmtree(scheduler_target)
        shutil.copytree(
            scheduler_source,
            scheduler_target,
            ignore=shutil.ignore_patterns("commented", "tests", "__pycache__"),
        )
    spec_path = local_root / "simulation.json"
    spec = {
        "schema_version": 1,
        "simulation": simulation_name,
        "processes": [
            {
                "name": process.name,
                "image": process.image,
                "env_file": _relative_to_workspace(
                    workspace_root,
                    process.env_file,
                ),
                "config_file": _relative_to_workspace(
                    workspace_root,
                    process.config_file,
                ),
                "cpus": process.cpus,
                "memory": process.memory,
            }
            for process in processes
        ],
    }
    spec_path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    compose_name = (
        "compose.simulate.bind.yaml"
        if volume_mode == "bind"
        else "compose.simulate.yaml"
    )
    compose_path = local_root / compose_name
    compose_path.write_text(
        _render_compose(
            workspace_root=workspace_root,
            local_root=local_root,
            spec_path=spec_path,
            project_name=project_name,
            simulation_name=simulation_name,
            volume_mode=volume_mode,
            bind_runtime=bind_runtime.resolve(),
        ),
        encoding="utf-8",
    )
    return compose_path


# Impide que el scheduler lea archivos fuera del workspace declarado.
def _relative_to_workspace(workspace_root: Path, path: Path) -> str:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(workspace_root)
    except ValueError as error:
        raise LocalSimulationError(
            f"Simulation path must belong to workspace {workspace_root}: {resolved}"
        ) from error
    return relative.as_posix()


def _relative_for_compose(local_root: Path, path: Path) -> str:
    return Path(os.path.relpath(path, local_root)).as_posix()


def _quoted(value: str) -> str:
    return json.dumps(value)


# Renderiza sólo el scheduler; los jobs se crean efímeramente por Docker.
def _render_compose(
    *,
    workspace_root: Path,
    local_root: Path,
    spec_path: Path,
    project_name: str,
    simulation_name: str,
    volume_mode: str,
    bind_runtime: Path,
) -> str:
    workspace_source = _relative_for_compose(local_root, workspace_root)
    spec_relative = _relative_to_workspace(workspace_root, spec_path)
    scheduler_image = f"atlanticus-{simulation_name}-scheduler:local"
    runtime_lines: tuple[str, ...]
    volume_suffix = ""
    if volume_mode == "named":
        runtime_lines = (
            "      - type: volume",
            "        source: runtime",
            f"        target: {RUNTIME_TARGET}",
        )
        volume_suffix = "\nvolumes:\n  runtime:\n"
    else:
        bind_source = _relative_for_compose(local_root, bind_runtime)
        runtime_lines = (
            "      - type: bind",
            f"        source: {_quoted(bind_source)}",
            f"        target: {RUNTIME_TARGET}",
        )
    lines = [
        f"name: {project_name}",
        "services:",
        "  scheduler:",
        f"    image: {scheduler_image}",
        "    build:",
        "      context: ./scheduler",
        "      dockerfile: Dockerfile",
        '    restart: "unless-stopped"',
        "    environment:",
        f"      ATLANTICUS_SIMULATION: {_quoted(simulation_name)}",
        f"      ATLANTICUS_SIMULATION_SPEC: {_quoted(f'{WORKSPACE_TARGET}/{spec_relative}')}",
        f"      DOCKER_HOST: {_quoted(f'unix://{DOCKER_SOCKET_TARGET}')}",
        '      TZ: "UTC"',
        "    labels:",
        f"      atlanticus.simulation: {_quoted(simulation_name)}",
        '      atlanticus.role: "scheduler"',
        "    volumes:",
        "      - type: bind",
        '        source: "${ATLANTICUS_DOCKER_SOCKET_SOURCE:-/var/run/docker.sock}"',
        f"        target: {DOCKER_SOCKET_TARGET}",
        "      - type: bind",
        f"        source: {_quoted(workspace_source)}",
        f"        target: {WORKSPACE_TARGET}",
        "        read_only: true",
        *runtime_lines,
    ]
    return "\n".join(lines) + "\n" + volume_suffix
