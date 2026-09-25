from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

PYTHON_VERSION = "3.14.2"
BOOTSTRAP_ENVIRONMENT_VARIABLE = "ATLANTICUS_DISTRIBUTION_TOOL_BOOTSTRAPPED"
BUNDLE_MODULE_NAME = "atlanticus_distribution_process_bundle"
PROCESS_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DISTRIBUTION_NAME_PATTERN = PROCESS_NAME_PATTERN
MEMORY_PATTERN = re.compile(r"^[1-9][0-9]*(?:\.[0-9]+)?[bkmg]?$", re.IGNORECASE)
REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
ALLOWED_SYSTEM_PROFILES = frozenset({"base", "sqlserver"})
DEFAULT_CPUS = 0.5
DEFAULT_MEMORY = "1g"
DEFAULT_VOLUME_PATH = "/app/volumen"
DISTRIBUTION_CONTRACT_KEY = "x-atlanticus-distribution-contract"
DISTRIBUTION_CONTRACT_VERSION = "1"
REQUIRED_ARTIFACT_ENTRIES = (
    "pyproject.toml",
    "uv.lock",
    "wheels",
    "src",
    ".env.detail",
    "config.detail.json",
    "secrets.detail.json",
)
CONSUMER_CONFIGURATION_FILES = (".env", "config.json", "secrets.json")
LOCAL_ONLY_NAMES = frozenset(
    {
        ".runtime",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        "build",
        "dist",
    }
)


class DistributionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProcessDeployment:
    number: str
    process: str
    excecution_file: str

    @property
    def container_name(self) -> str:
        return f"job{self.number}"

    @property
    def config_file(self) -> str:
        return f"processes/{self.excecution_file}/config.json"


@dataclass(frozen=True, slots=True)
class ProcessArtifact:
    name: str
    root: Path
    project_name: str
    project_version: str
    description: str
    runtime_version: str
    command: str
    system_profile: str
    cpus: float
    memory: str


@dataclass(frozen=True, slots=True)
class SelectedSource:
    process_root: Path
    deployment: ProcessDeployment


@dataclass(frozen=True, slots=True)
class SelectedProcess:
    artifact: ProcessArtifact
    deployment: ProcessDeployment


DEPLOYMENT_CATALOG = (
    ProcessDeployment("01", "operational-data-pi", "pi-web-api"),
    ProcessDeployment("02", "operational-data-notpii", "notpii"),
    ProcessDeployment("03", "operational-data-dispatch", "dispatch"),
    ProcessDeployment("04", "operational-data-blockgrade", "blockgrade"),
    ProcessDeployment("05", "operational-data-fabrica", "fabrica"),
    ProcessDeployment("06", "operational-data-remanentes", "remanentes"),
    ProcessDeployment("21", "ada-kpi-runtime", "kpis"),
    ProcessDeployment("22", "ada-kpi-historian", "kpis-historian"),
    ProcessDeployment("41", "ada-kpi-delivery", "kpis-delivery"),
    ProcessDeployment(
        "42",
        "ada-kpi-timeseries-delivery",
        "kpis-timeseries-delivery",
    ),
)
DEPLOYMENT_BY_PROCESS = {item.process: item for item in DEPLOYMENT_CATALOG}


def _repository_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "deployment/processes/Dockerfile").is_file() and (
            candidate / "deployment/processes/.dockerignore"
        ).is_file():
            return candidate
    raise DistributionError("Atlanticus repository root could not be resolved")


def _load_bundle(repository_root: Path) -> ModuleType:
    path = repository_root / "deployment/processes/bundle.py"
    spec = importlib.util.spec_from_file_location(BUNDLE_MODULE_NAME, path)
    if spec is None or spec.loader is None:
        raise DistributionError(f"Process bundle module could not be loaded: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _bootstrap(raw_argv: list[str]) -> None:
    if os.environ.get(BOOTSTRAP_ENVIRONMENT_VARIABLE) == "1":
        return
    if platform.python_version() == PYTHON_VERSION:
        return
    environment = os.environ.copy()
    environment[BOOTSTRAP_ENVIRONMENT_VARIABLE] = "1"
    command = [
        "uv",
        "run",
        "--python",
        PYTHON_VERSION,
        "--no-python-downloads",
        "--no-project",
        "python",
        str(Path(__file__).resolve()),
        *raw_argv,
    ]
    completed = subprocess.run(
        command,
        cwd=Path.cwd(),
        env=environment,
        check=False,
    )
    raise SystemExit(completed.returncode)


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as stream:
            return tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise DistributionError(f"Could not read TOML file: {path}") from error


def _container_metadata(
    metadata: dict[str, Any],
    pyproject_path: Path,
) -> tuple[str, str, float, str]:
    project = metadata.get("project")
    if not isinstance(project, dict):
        raise DistributionError(f"Project metadata is invalid: {pyproject_path}")
    scripts = project.get("scripts")
    if not isinstance(scripts, dict):
        raise DistributionError(f"Project entrypoints are invalid: {pyproject_path}")
    tool = metadata.get("tool")
    atlanticus = tool.get("atlanticus") if isinstance(tool, dict) else None
    container = atlanticus.get("container") if isinstance(atlanticus, dict) else None
    if not isinstance(container, dict):
        raise DistributionError(f"Container metadata is missing: {pyproject_path}")
    command = container.get("command")
    system_profile = container.get("system-profile")
    if not isinstance(command, str) or not PROCESS_NAME_PATTERN.fullmatch(command):
        raise DistributionError(f"Container command is invalid: {pyproject_path}")
    if command not in scripts:
        raise DistributionError(
            f"Container command is not declared as a project entrypoint: {pyproject_path}"
        )
    if system_profile not in ALLOWED_SYSTEM_PROFILES:
        raise DistributionError(
            f"Container system profile is invalid: {pyproject_path}"
        )
    resources = container.get("resources", {})
    if not isinstance(resources, dict):
        raise DistributionError(f"Container resources are invalid: {pyproject_path}")
    cpus = resources.get("cpus", DEFAULT_CPUS)
    memory = resources.get("memory", DEFAULT_MEMORY)
    if isinstance(cpus, bool) or not isinstance(cpus, (int, float)) or cpus <= 0:
        raise DistributionError(
            f"Container cpus must be greater than zero: {pyproject_path}"
        )
    if not isinstance(memory, str) or not MEMORY_PATTERN.fullmatch(memory):
        raise DistributionError(f"Container memory is invalid: {pyproject_path}")
    return command, system_profile, float(cpus), memory.lower()


def _load_artifact(
    root: Path,
    *,
    require_directory_match: bool = True,
) -> ProcessArtifact:
    for relative in REQUIRED_ARTIFACT_ENTRIES:
        if not (root / relative).exists():
            raise DistributionError(
                f"Process transport artifact is incomplete ({relative}): {root}"
            )
    if not (root / "wheels").is_dir() or not (root / "src").is_dir():
        raise DistributionError(
            f"Process transport artifact directories are invalid: {root}"
        )
    metadata = _read_toml(root / "pyproject.toml")
    project = metadata.get("project")
    if not isinstance(project, dict):
        raise DistributionError(
            f"Project metadata is invalid: {root / 'pyproject.toml'}"
        )
    project_name = project.get("name")
    project_version = project.get("version")
    description = project.get("description")
    requires_python = project.get("requires-python")
    if not isinstance(project_name, str) or not project_name:
        raise DistributionError(f"Project name is invalid: {root / 'pyproject.toml'}")
    if not isinstance(project_version, str) or not project_version:
        raise DistributionError(
            f"Project version is invalid: {root / 'pyproject.toml'}"
        )
    if not isinstance(description, str) or not description.strip():
        raise DistributionError(
            f"Project description is invalid: {root / 'pyproject.toml'}"
        )
    expected_python = f"=={PYTHON_VERSION}"
    if requires_python != expected_python:
        raise DistributionError(
            f"Process artifact must require Python {PYTHON_VERSION}: "
            f"{root / 'pyproject.toml'}"
        )
    command, system_profile, cpus, memory = _container_metadata(
        metadata,
        root / "pyproject.toml",
    )
    if require_directory_match and root.name != command:
        raise DistributionError(
            f"Process artifact directory must match container command: {root}"
        )
    return ProcessArtifact(
        name=command,
        root=root,
        project_name=project_name,
        project_version=project_version,
        description=description.strip(),
        runtime_version=requires_python.removeprefix("=="),
        command=command,
        system_profile=system_profile,
        cpus=cpus,
        memory=memory,
    )


def _target_candidates(repository_root: Path, target: str) -> tuple[Path, ...]:
    candidates = [repository_root / "scopes" / target / "processes"]
    if target.endswith("-backend"):
        scope = target.removesuffix("-backend")
        if scope:
            candidates.append(repository_root / "scopes" / scope / "backend/processes")
    return tuple(dict.fromkeys(path.resolve() for path in candidates))


def _target_commands(repository_root: Path, target: str) -> tuple[str, ...]:
    matches = tuple(
        candidate
        for candidate in _target_candidates(repository_root, target)
        if candidate.is_dir()
    )
    if not matches:
        raise DistributionError(f"Unknown process target: {target}")
    if len(matches) != 1:
        rendered = ", ".join(str(path) for path in matches)
        raise DistributionError(f"Ambiguous process target {target}: {rendered}")
    commands: list[str] = []
    for pyproject_path in sorted(matches[0].glob("*/pyproject.toml")):
        metadata = _read_toml(pyproject_path)
        tool = metadata.get("tool")
        atlanticus = tool.get("atlanticus") if isinstance(tool, dict) else None
        container = (
            atlanticus.get("container") if isinstance(atlanticus, dict) else None
        )
        if not isinstance(container, dict):
            continue
        command, _, _, _ = _container_metadata(metadata, pyproject_path)
        commands.append(command)
    if not commands:
        raise DistributionError(f"No exportable processes found for target: {target}")
    return tuple(commands)


def _resolve_selection(
    *,
    repository_root: Path,
    bundle: ModuleType,
    selections: tuple[str, ...],
    targets: tuple[str, ...],
) -> tuple[SelectedSource, ...]:
    requested: list[str] = list(selections)
    for target in targets:
        requested.extend(_target_commands(repository_root, target))
    if not requested:
        raise DistributionError(
            "Select at least one process or provide one or more --target values"
        )
    requested_names = frozenset(requested)
    unknown_deployments = tuple(
        name for name in requested_names if name not in DEPLOYMENT_BY_PROCESS
    )
    if unknown_deployments:
        raise DistributionError(
            "Process deployment slot is not registered: "
            + ", ".join(sorted(unknown_deployments))
        )
    return tuple(
        SelectedSource(
            process_root=bundle.resolve_process_root(repository_root, item.process),
            deployment=item,
        )
        for item in DEPLOYMENT_CATALOG
        if item.process in requested_names
    )


def _artifact_ignore(directory: str, names: list[str]) -> set[str]:
    ignored = {name for name in names if name in LOCAL_ONLY_NAMES}
    ignored.update(name for name in names if name.endswith(".egg-info"))
    ignored.update(
        name for name in names if name.startswith(".env.") and name != ".env.detail"
    )
    ignored.update(name for name in names if name in CONSUMER_CONFIGURATION_FILES)
    return ignored


def _preserve_consumer_configuration(
    current_root: Path,
    staged_process: Path,
    excecution_file: str,
) -> None:
    current_process = current_root / "processes" / excecution_file
    for name in CONSUMER_CONFIGURATION_FILES:
        current = current_process / name
        if current.is_file():
            shutil.copy2(current, staged_process / name)


def _render_service(
    distribution_name: str,
    selected: SelectedProcess,
    *,
    volume_mode: str,
) -> str:
    alias = selected.deployment.excecution_file
    artifact = selected.artifact
    volume_source = "runtime" if volume_mode == "named" else "../../.runtime/volumen"
    return "\n".join(
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
            f"      VOLUMEN_PATH: {DEFAULT_VOLUME_PATH}",
            "    volumes:",
            f"      - {volume_source}:{DEFAULT_VOLUME_PATH}",
            f"    cpus: {artifact.cpus:g}",
            f"    mem_limit: {artifact.memory}",
        )
    )


def _render_compose(
    distribution_name: str,
    selected: tuple[SelectedProcess, ...],
    *,
    volume_mode: str,
) -> str:
    if volume_mode not in {"named", "bind"}:
        raise DistributionError(f"Unsupported volume mode: {volume_mode}")
    services = "\n".join(
        _render_service(distribution_name, item, volume_mode=volume_mode)
        for item in selected
    )
    volumes = "\nvolumes:\n  runtime:\n" if volume_mode == "named" else ""
    return (
        f"name: atlanticus-{distribution_name}-local\n"
        f'{DISTRIBUTION_CONTRACT_KEY}: "{DISTRIBUTION_CONTRACT_VERSION}"\n'
        f"services:\n{services}\n{volumes}"
    )


def _generated_at() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _source_revision(repository_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise DistributionError(
            f"Could not resolve source revision: {repository_root}"
        ) from error
    revision = completed.stdout.strip()
    if REVISION_PATTERN.fullmatch(revision) is None:
        raise DistributionError(f"Source revision is invalid: {revision}")
    return revision


def _manifest(
    distribution_name: str,
    selected: tuple[SelectedProcess, ...],
    *,
    generated_at: str,
    source_revision: str,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "name": distribution_name,
        "generated_at": generated_at,
        "source": {
            "repository": "atlanticus",
            "revision": source_revision,
        },
        "processes": [
            {
                "process": item.artifact.command,
                "project": item.artifact.project_name,
                "version": item.artifact.project_version,
                "description": item.artifact.description,
                "runtime": {
                    "language": "python",
                    "version": item.artifact.runtime_version,
                },
                "deployment": {
                    "excecution_file": item.deployment.excecution_file,
                    "container_name": item.deployment.container_name,
                },
            }
            for item in selected
        ],
    }


def _service(item: SelectedProcess) -> dict[str, object]:
    deployment = item.deployment
    return {
        "repository": deployment.excecution_file,
        "excecution_file": deployment.excecution_file,
        "container_name": deployment.container_name,
        "config_file": deployment.config_file,
        "to_deploy": True,
        "to_stop": False,
        "to_working_hours_dev": True,
        "to_working_hours_uat": True,
    }


def _services(selected: tuple[SelectedProcess, ...]) -> list[dict[str, object]]:
    return [_service(item) for item in selected]


def _consumer_template_root() -> Path:
    return Path(__file__).resolve().parent / "consumer"


def _copy_consumer_tooling(staging_root: Path) -> None:
    source = _consumer_template_root()
    target = staging_root / "tooling/local/processes"
    target.mkdir(parents=True)
    for name in ("process.py", "process.sh", "process.cmd"):
        source_path = source / name
        if not source_path.is_file():
            raise DistributionError(
                f"Consumer process tool template not found: {source_path}"
            )
        shutil.copy2(source_path, target / name)


def _copy_local_deployment_capability(
    repository_root: Path,
    staging_root: Path,
) -> Path:
    source = repository_root / "deployment/local"
    target = staging_root / "deployment/local"
    target.mkdir(parents=True, exist_ok=True)
    simulation_source = source / "simulation.py"
    scheduler_source = source / "scheduler"
    if not simulation_source.is_file():
        raise DistributionError(
            f"Local simulation capability not found: {simulation_source}"
        )
    if (
        not (scheduler_source / "Dockerfile").is_file()
        or not (scheduler_source / "scheduler.py").is_file()
    ):
        raise DistributionError(
            f"Local scheduler capability is incomplete: {scheduler_source}"
        )
    shutil.copy2(simulation_source, target / "simulation.py")
    shutil.copytree(
        scheduler_source,
        target / "scheduler",
        ignore=shutil.ignore_patterns("commented", "tests", "__pycache__"),
    )
    return target


def _validate_staging(
    *,
    staging_root: Path,
    distribution_name: str,
    selected: tuple[SelectedProcess, ...],
    generated_at: str,
    source_revision: str,
) -> None:
    expected_aliases = tuple(item.deployment.excecution_file for item in selected)
    actual_aliases = tuple(
        sorted(
            path.name
            for path in (staging_root / "processes").iterdir()
            if path.is_dir()
        )
    )
    if actual_aliases != tuple(sorted(expected_aliases)):
        raise DistributionError(
            "Staged process set does not match the declared composition"
        )
    for item in selected:
        staged = _load_artifact(
            staging_root / "processes" / item.deployment.excecution_file,
            require_directory_match=False,
        )
        if staged.command != item.artifact.command:
            raise DistributionError(
                f"Staged process command is invalid: {item.deployment.excecution_file}"
            )
    manifest_path = staging_root / "distribution.json"
    services_path = staging_root / "services.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        services = json.loads(services_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DistributionError("Generated distribution JSON is invalid") from error
    expected_manifest = _manifest(
        distribution_name,
        selected,
        generated_at=generated_at,
        source_revision=source_revision,
    )
    if manifest != expected_manifest:
        raise DistributionError(
            "Generated distribution manifest does not match the selection"
        )
    if services != _services(selected):
        raise DistributionError(
            "Generated services manifest does not match the deployment catalog"
        )
    local_root = staging_root / "deployment/local"
    for compose_name in ("compose.yaml", "compose.bind.yaml"):
        compose = (local_root / compose_name).read_text(encoding="utf-8")
        marker = f'{DISTRIBUTION_CONTRACT_KEY}: "{DISTRIBUTION_CONTRACT_VERSION}"'
        if marker not in compose:
            raise DistributionError(
                f"Generated Compose contract is invalid: {compose_name}"
            )
        for alias in expected_aliases:
            if f"  {alias}:" not in compose or f"FILENAME: {alias}" not in compose:
                raise DistributionError(
                    f"Generated Compose is missing deployment alias {alias}: {compose_name}"
                )
    if (staging_root / "compose.yaml").exists() or (
        staging_root / "compose.bind.yaml"
    ).exists():
        raise DistributionError(
            "Local Compose files must not live at distribution root"
        )
    for required in (
        local_root / "simulation.py",
        local_root / "scheduler/Dockerfile",
        local_root / "scheduler/scheduler.py",
    ):
        if not required.is_file():
            raise DistributionError(
                f"Generated local deployment capability is missing: {required}"
            )
    if (staging_root / ".runtime").exists():
        raise DistributionError("Generated distribution must not contain .runtime")
    for name in ("process.py", "process.sh", "process.cmd"):
        if not (staging_root / "tooling/local/processes" / name).is_file():
            raise DistributionError(
                f"Generated consumer process tool is missing: {name}"
            )


def _replace_directory(source: Path, target: Path) -> None:
    replacement = target.with_name(f".{target.name}.atlanticus-{uuid.uuid4().hex}.new")
    backup = target.with_name(f".{target.name}.atlanticus-{uuid.uuid4().hex}.backup")
    shutil.copytree(source, replacement)
    had_target = target.exists()
    try:
        if had_target:
            os.replace(target, backup)
        os.replace(replacement, target)
    except BaseException:
        if replacement.exists():
            shutil.rmtree(replacement)
        if had_target and backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def distribute(
    *,
    repository_root: Path,
    output_root: Path,
    distribution_name: str,
    selections: tuple[str, ...],
    targets: tuple[str, ...],
    bundle: ModuleType | None = None,
) -> Path:
    if not DISTRIBUTION_NAME_PATTERN.fullmatch(distribution_name):
        raise DistributionError(f"Invalid distribution name: {distribution_name}")
    repository_root = repository_root.resolve()
    bundle = _load_bundle(repository_root) if bundle is None else bundle
    try:
        selected_sources = _resolve_selection(
            repository_root=repository_root,
            bundle=bundle,
            selections=selections,
            targets=targets,
        )
        for item in selected_sources:
            bundle.require_prepared_build_inputs(
                repository_root,
                item.process_root,
            )
    except bundle.ProcessBundleError as error:
        raise DistributionError(str(error)) from error
    generated_at = _generated_at()
    source_revision = _source_revision(repository_root)
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    target_root = output_root / distribution_name
    temporary = Path(
        tempfile.mkdtemp(prefix=f"atlanticus-{distribution_name}-distribution-")
    )
    try:
        bundle_root = temporary / "bundles"
        selected: list[SelectedProcess] = []
        try:
            for item in selected_sources:
                rebuilt = bundle.build_process_bundle(
                    repository_root=repository_root,
                    process_root=item.process_root,
                    output_root=bundle_root,
                )
                bundle.require_prepared_build_inputs(
                    repository_root,
                    item.process_root,
                )
                artifact = _load_artifact(rebuilt)
                if artifact.command != item.deployment.process:
                    raise DistributionError(
                        "Rebuilt process command does not match deployment catalog: "
                        f"{artifact.command}"
                    )
                selected.append(
                    SelectedProcess(
                        artifact=artifact,
                        deployment=item.deployment,
                    )
                )
        except bundle.ProcessBundleError as error:
            raise DistributionError(str(error)) from error
        selected_processes = tuple(selected)
        staging_root = temporary / distribution_name
        staging_root.mkdir()
        shutil.copy2(
            repository_root / "deployment/processes/Dockerfile",
            staging_root / "Dockerfile",
        )
        shutil.copy2(
            repository_root / "deployment/processes/.dockerignore",
            staging_root / ".dockerignore",
        )
        processes_root = staging_root / "processes"
        processes_root.mkdir()
        for item in selected_processes:
            alias = item.deployment.excecution_file
            staged_process = processes_root / alias
            shutil.copytree(
                item.artifact.root,
                staged_process,
                ignore=_artifact_ignore,
            )
            _preserve_consumer_configuration(
                target_root,
                staged_process,
                alias,
            )
        (staging_root / "distribution.json").write_text(
            json.dumps(
                _manifest(
                    distribution_name,
                    selected_processes,
                    generated_at=generated_at,
                    source_revision=source_revision,
                ),
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (staging_root / "services.json").write_text(
            json.dumps(_services(selected_processes), indent=2) + "\n",
            encoding="utf-8",
        )
        local_root = _copy_local_deployment_capability(
            repository_root,
            staging_root,
        )
        (local_root / "compose.yaml").write_text(
            _render_compose(
                distribution_name,
                selected_processes,
                volume_mode="named",
            ),
            encoding="utf-8",
        )
        (local_root / "compose.bind.yaml").write_text(
            _render_compose(
                distribution_name,
                selected_processes,
                volume_mode="bind",
            ),
            encoding="utf-8",
        )
        _copy_consumer_tooling(staging_root)
        _validate_staging(
            staging_root=staging_root,
            distribution_name=distribution_name,
            selected=selected_processes,
            generated_at=generated_at,
            source_revision=source_revision,
        )
        _replace_directory(staging_root, target_root)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    return target_root


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a declarative consumer distribution from prepared process source."
    )
    parser.add_argument("distribution")
    parser.add_argument("processes", nargs="*")
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        help="Include every process belonging to one logical source target.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        help="Output root. Defaults to distribution at the Atlanticus repository root.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    _bootstrap(raw_argv)
    arguments = _parser().parse_args(raw_argv)
    repository_root = _repository_root()
    output_root = (
        arguments.output_root
        if arguments.output_root is not None
        else repository_root / "distribution"
    )
    try:
        target = distribute(
            repository_root=repository_root,
            output_root=output_root,
            distribution_name=arguments.distribution,
            selections=tuple(arguments.processes),
            targets=tuple(arguments.target),
        )
    except DistributionError as error:
        raise SystemExit(str(error)) from error
    print(f"Distribution package: {target}")
    print(f"Configure process files under: {target / 'processes'}")
    print(f"Pipeline manifest: {target / 'services.json'}")
    print(f"Local validation: {target / 'tooling/local/processes/process.sh'} validate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
