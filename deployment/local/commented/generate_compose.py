# Genera un workspace Docker Compose temporal desde artifacts transportables certificados.
# La configuración activa permanece fuera del contexto de build y se inyecta en runtime.
# El contrato fuente/artifact se compara antes de construir y el workspace generado se versiona
# para impedir que run reutilice silenciosamente un Compose perteneciente a una revisión anterior.
from __future__ import annotations

import argparse
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomllib

DEFAULT_CPUS = 0.5
DEFAULT_MEMORY = "1g"
DEFAULT_VOLUME_PATH = "/app/volumen"
DEFAULT_WORKSPACE = Path(".runtime/local-deployment")
PROJECT_NAME = "atlanticus-processes-local"
RUNTIME_VOLUME_KEY = "runtime"
LOCAL_WORKSPACE_CONTRACT_KEY = "x-atlanticus-local-contract"
LOCAL_WORKSPACE_CONTRACT_VERSION = "2"
LEGACY_VOLUME_PATH = "/app/volume"
SOURCE_PROCESS_PATTERNS = (
    "scopes/*/processes/*/pyproject.toml",
    "scopes/*/backend/processes/*/pyproject.toml",
)
PROCESS_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MEMORY_PATTERN = re.compile(r"^[1-9][0-9]*(?:\.[0-9]+)?[bkmg]?$", re.IGNORECASE)
ALLOWED_SYSTEM_PROFILES = frozenset({"base", "sqlserver"})


class LocalDeploymentError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProcessContract:
    project_name: str
    project_version: str
    requires_python: str
    dependencies: tuple[str, ...]
    scripts: tuple[tuple[str, str], ...]
    command: str
    system_profile: str
    cpus: float
    memory: str


@dataclass(frozen=True, slots=True)
class ProcessDefinition:
    name: str
    env_file: Path
    artifact_root: Path
    contract: ProcessContract

    @property
    def command(self) -> str:
        return self.contract.command

    @property
    def system_profile(self) -> str:
        return self.contract.system_profile

    @property
    def cpus(self) -> float:
        return self.contract.cpus

    @property
    def memory(self) -> str:
        return self.contract.memory


# Descubre exclusivamente artifacts ya preparados; el nombre físico sigue siendo el command.
def discover_processes(repository_root: Path) -> tuple[ProcessDefinition, ...]:
    artifacts_root = repository_root / "artifacts" / "processes"
    if not artifacts_root.is_dir():
        raise LocalDeploymentError(
            f"process artifacts directory not found: {artifacts_root}. "
            "Run: scripts/local-process.sh prepare"
        )
    definitions: list[ProcessDefinition] = []
    for pyproject_path in sorted(artifacts_root.glob("*/pyproject.toml")):
        name = pyproject_path.parent.name
        if not PROCESS_NAME_PATTERN.fullmatch(name):
            raise LocalDeploymentError(
                f"invalid process artifact directory name: {name}"
            )
        metadata = _read_toml(pyproject_path)
        contract = _process_contract(metadata, pyproject_path)
        if contract is None:
            continue
        if contract.command != name:
            raise LocalDeploymentError(
                f"process artifact directory must match container command: {pyproject_path.parent}"
            )
        definitions.append(
            ProcessDefinition(
                name=name,
                env_file=pyproject_path.parent / ".env",
                artifact_root=pyproject_path.parent,
                contract=contract,
            )
        )
    if not definitions:
        raise LocalDeploymentError(f"no process artifacts found: {artifacts_root}")
    return tuple(definitions)


def validate_environment_files(definitions: tuple[ProcessDefinition, ...]) -> None:
    missing = tuple(
        definition.env_file
        for definition in definitions
        if not definition.env_file.is_file()
    )
    if missing:
        rendered = "\n".join(f"  - {path}" for path in missing)
        raise LocalDeploymentError(
            "local artifact .env file not found:\n"
            f"{rendered}\n"
            "Configure each artifact before running local deployment."
        )


def validate_artifacts(definitions: tuple[ProcessDefinition, ...]) -> None:
    for definition in definitions:
        artifact_root = definition.artifact_root
        for relative in ("pyproject.toml", "uv.lock", "wheels", "src"):
            path = artifact_root / relative
            if not path.exists():
                raise LocalDeploymentError(
                    f"process transport artifact is incomplete ({relative}): {artifact_root}"
                )


# Compara sólo el contrato declarativo del process; no exige un git working tree limpio.
def validate_source_contracts(
    repository_root: Path,
    definitions: tuple[ProcessDefinition, ...],
) -> None:
    sources: dict[str, tuple[ProcessContract, Path]] = {}
    for pattern in SOURCE_PROCESS_PATTERNS:
        for pyproject_path in sorted(repository_root.glob(pattern)):
            contract = _process_contract(_read_toml(pyproject_path), pyproject_path)
            if contract is None:
                continue
            previous = sources.get(contract.command)
            if previous is not None:
                raise LocalDeploymentError(
                    f"duplicate source process container command {contract.command}: "
                    f"{previous[1].parent} and {pyproject_path.parent}"
                )
            sources[contract.command] = (contract, pyproject_path)
    for definition in definitions:
        source = sources.get(definition.command)
        if source is None:
            raise LocalDeploymentError(
                f"source process contract not found for artifact {definition.name}. "
                f"Run: scripts/local-process.sh prepare {definition.name}"
            )
        source_contract, source_path = source
        if source_contract != definition.contract:
            raise LocalDeploymentError(
                f"process artifact contract is stale for {definition.name}: "
                f"source {_contract_summary(source_contract)} at {source_path.parent}; "
                f"artifact {_contract_summary(definition.contract)} at {definition.artifact_root}. "
                f"Run: scripts/local-process.sh prepare {definition.name}"
            )


# El marcador evita reutilizar un Compose previo cuando cambió el contrato del deployment local.
def validate_workspace_contract(workspace_root: Path) -> None:
    compose_path = workspace_root / "compose.yaml"
    if not compose_path.is_file():
        raise LocalDeploymentError(
            "local Compose workspace not found. Run: scripts/local-process.sh build"
        )
    try:
        compose = compose_path.read_text(encoding="utf-8")
    except OSError as error:
        raise LocalDeploymentError(
            f"could not read local Compose workspace: {compose_path}"
        ) from error
    marker = f'{LOCAL_WORKSPACE_CONTRACT_KEY}: "{LOCAL_WORKSPACE_CONTRACT_VERSION}"'
    if marker in compose:
        return
    if LEGACY_VOLUME_PATH in compose:
        raise LocalDeploymentError(
            f"local deployment workspace contract is stale: legacy volume path "
            f"{LEGACY_VOLUME_PATH} was detected. Run: scripts/local-process.sh build"
        )
    raise LocalDeploymentError(
        "local deployment workspace contract is stale or unsupported. "
        "Run: scripts/local-process.sh build"
    )


def prepare_workspace(
    *,
    repository_root: Path,
    workspace_root: Path,
    definitions: tuple[ProcessDefinition, ...],
    volume_mode: str,
) -> Path:
    if volume_mode not in {"named", "bind"}:
        raise LocalDeploymentError(f"unsupported local volume mode: {volume_mode}")
    validate_artifacts(definitions)
    validate_environment_files(definitions)
    workspace_root.mkdir(parents=True, exist_ok=True)
    for generated in (
        workspace_root / "Dockerfile",
        workspace_root / ".dockerignore",
        workspace_root / "compose.yaml",
        workspace_root / "compose",
        workspace_root / "processes",
    ):
        if generated.is_dir():
            shutil.rmtree(generated)
        elif generated.exists():
            generated.unlink()
    if volume_mode == "bind":
        (workspace_root / "runtime").mkdir(parents=True, exist_ok=True)
    docker_source = repository_root / "deployment" / "processes"
    shutil.copy2(docker_source / "Dockerfile", workspace_root / "Dockerfile")
    shutil.copy2(docker_source / ".dockerignore", workspace_root / ".dockerignore")
    processes_root = workspace_root / "processes"
    processes_root.mkdir()
    for definition in definitions:
        shutil.copytree(
            definition.artifact_root,
            processes_root / definition.name,
            ignore=shutil.ignore_patterns(".env", "config.json", "secrets.json"),
        )
    compose_root = workspace_root / "compose"
    compose_root.mkdir()
    for definition in definitions:
        (compose_root / f"{definition.name}.yaml").write_text(
            _render_fragment(
                definition, workspace_root=workspace_root, volume_mode=volume_mode
            ),
            encoding="utf-8",
        )
    compose_path = workspace_root / "compose.yaml"
    compose_path.write_text(
        _render_compose(
            definitions, workspace_root=workspace_root, volume_mode=volume_mode
        ),
        encoding="utf-8",
    )
    return compose_path


def _process_contract(
    metadata: dict[str, Any],
    pyproject_path: Path,
) -> ProcessContract | None:
    project = metadata.get("project")
    if not isinstance(project, dict):
        raise LocalDeploymentError(f"project metadata is invalid: {pyproject_path}")
    project_name = project.get("name")
    project_version = project.get("version")
    requires_python = project.get("requires-python")
    dependencies = project.get("dependencies", [])
    scripts = project.get("scripts", {})
    if not isinstance(project_name, str) or not project_name:
        raise LocalDeploymentError(f"project name is invalid: {pyproject_path}")
    if not isinstance(project_version, str) or not project_version:
        raise LocalDeploymentError(f"project version is invalid: {pyproject_path}")
    if not isinstance(requires_python, str) or not requires_python:
        raise LocalDeploymentError(
            f"project Python requirement is invalid: {pyproject_path}"
        )
    if not isinstance(dependencies, list) or not all(
        isinstance(item, str) for item in dependencies
    ):
        raise LocalDeploymentError(
            f"project dependencies are invalid: {pyproject_path}"
        )
    if not isinstance(scripts, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in scripts.items()
    ):
        raise LocalDeploymentError(f"project scripts are invalid: {pyproject_path}")
    container = _container_metadata(metadata, pyproject_path)
    if container is None:
        return None
    command, system_profile, cpus, memory = container
    return ProcessContract(
        project_name=project_name,
        project_version=project_version,
        requires_python=requires_python,
        dependencies=tuple(dependencies),
        scripts=tuple(sorted(scripts.items())),
        command=command,
        system_profile=system_profile,
        cpus=cpus,
        memory=memory,
    )


def _container_metadata(
    metadata: dict[str, Any],
    pyproject_path: Path,
) -> tuple[str, str, float, str] | None:
    tool = metadata.get("tool")
    if not isinstance(tool, dict):
        return None
    atlanticus = tool.get("atlanticus")
    if not isinstance(atlanticus, dict):
        return None
    container = atlanticus.get("container")
    if not isinstance(container, dict):
        return None
    command = container.get("command")
    system_profile = container.get("system-profile")
    if not isinstance(command, str) or not command:
        raise LocalDeploymentError(f"container command is invalid: {pyproject_path}")
    if system_profile not in ALLOWED_SYSTEM_PROFILES:
        raise LocalDeploymentError(
            f"container system profile is invalid: {pyproject_path}"
        )
    resources = container.get("resources", {})
    if not isinstance(resources, dict):
        raise LocalDeploymentError(
            f"container resources must be a table: {pyproject_path}"
        )
    cpus = resources.get("cpus", DEFAULT_CPUS)
    memory = resources.get("memory", DEFAULT_MEMORY)
    if isinstance(cpus, bool) or not isinstance(cpus, (int, float)) or cpus <= 0:
        raise LocalDeploymentError(
            f"container cpus must be greater than zero: {pyproject_path}"
        )
    if not isinstance(memory, str) or not MEMORY_PATTERN.fullmatch(memory):
        raise LocalDeploymentError(f"container memory is invalid: {pyproject_path}")
    return command, system_profile, float(cpus), memory.lower()


def _contract_summary(contract: ProcessContract) -> str:
    return (
        f"{contract.project_name}=={contract.project_version} "
        f"command={contract.command} profile={contract.system_profile}"
    )


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise LocalDeploymentError(f"could not read TOML file: {path}") from error


def _render_service(
    definition: ProcessDefinition,
    *,
    workspace_root: Path,
    volume_mode: str,
    indent: str,
) -> str:
    env_path = Path(os.path.relpath(definition.env_file, workspace_root)).as_posix()
    volume_source = RUNTIME_VOLUME_KEY if volume_mode == "named" else "./runtime"
    return "\n".join(
        (
            f"{indent}{definition.name}:",
            f"{indent}  image: atlanticus-{definition.name}:local",
            f"{indent}  build:",
            f"{indent}    context: .",
            f"{indent}    dockerfile: Dockerfile",
            f"{indent}    args:",
            f"{indent}      FILENAME: {definition.name}",
            f'{indent}  command: ["--run-once"]',
            f'{indent}  restart: "no"',
            f"{indent}  env_file:",
            f"{indent}    - {env_path}",
            f"{indent}  environment:",
            f"{indent}    VOLUMEN_PATH: {DEFAULT_VOLUME_PATH}",
            f"{indent}  volumes:",
            f"{indent}    - {volume_source}:{DEFAULT_VOLUME_PATH}",
            f"{indent}  cpus: {definition.cpus:g}",
            f"{indent}  mem_limit: {definition.memory}",
        )
    )


def _render_fragment(
    definition: ProcessDefinition,
    *,
    workspace_root: Path,
    volume_mode: str,
) -> str:
    return (
        "services:\n"
        + _render_service(
            definition,
            workspace_root=workspace_root,
            volume_mode=volume_mode,
            indent="  ",
        )
        + "\n"
    )


def _render_compose(
    definitions: tuple[ProcessDefinition, ...],
    *,
    workspace_root: Path,
    volume_mode: str,
) -> str:
    services = "\n".join(
        _render_service(
            definition,
            workspace_root=workspace_root,
            volume_mode=volume_mode,
            indent="  ",
        )
        for definition in definitions
    )
    suffix = f"\nvolumes:\n  {RUNTIME_VOLUME_KEY}:\n" if volume_mode == "named" else ""
    return (
        f"name: {PROJECT_NAME}\n"
        f'{LOCAL_WORKSPACE_CONTRACT_KEY}: "{LOCAL_WORKSPACE_CONTRACT_VERSION}"\n'
        f"services:\n{services}\n{suffix}"
    )


def _repository_root_from_script() -> Path:
    return Path(__file__).resolve().parents[2]


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare the Atlanticus local Compose workspace."
    )
    parser.add_argument(
        "action",
        choices=("validate", "validate-workspace", "generate"),
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=_repository_root_from_script(),
    )
    parser.add_argument("--workspace-root", type=Path)
    parser.add_argument("--volume-mode", choices=("named", "bind"), default="named")
    return parser.parse_args()


def main() -> None:
    arguments = _parse_arguments()
    repository_root = arguments.repository_root.resolve()
    workspace_root = (
        arguments.workspace_root.resolve()
        if arguments.workspace_root is not None
        else repository_root / DEFAULT_WORKSPACE
    )
    if arguments.action == "validate-workspace":
        validate_workspace_contract(workspace_root)
        return
    definitions = discover_processes(repository_root)
    validate_artifacts(definitions)
    validate_source_contracts(repository_root, definitions)
    validate_environment_files(definitions)
    if arguments.action == "validate":
        return
    compose_path = prepare_workspace(
        repository_root=repository_root,
        workspace_root=workspace_root,
        definitions=definitions,
        volume_mode=arguments.volume_mode,
    )
    print(compose_path)


if __name__ == "__main__":
    try:
        main()
    except LocalDeploymentError as error:
        raise SystemExit(str(error)) from error
