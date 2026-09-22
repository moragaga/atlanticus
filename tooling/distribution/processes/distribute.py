from __future__ import annotations

import argparse
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
from pathlib import Path
from typing import Any

PYTHON_VERSION = "3.14.2"
BOOTSTRAP_ENVIRONMENT_VARIABLE = "ATLANTICUS_DISTRIBUTION_TOOL_BOOTSTRAPPED"
PROCESS_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DISTRIBUTION_NAME_PATTERN = PROCESS_NAME_PATTERN
MEMORY_PATTERN = re.compile(r"^[1-9][0-9]*(?:\.[0-9]+)?[bkmg]?$", re.IGNORECASE)
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
class ProcessArtifact:
    name: str
    root: Path
    project_name: str
    project_version: str
    command: str
    system_profile: str
    cpus: float
    memory: str


def _repository_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "deployment/processes/Dockerfile").is_file() and (
            candidate / "deployment/processes/.dockerignore"
        ).is_file():
            return candidate
    raise DistributionError("Atlanticus repository root could not be resolved")


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


def _load_artifact(root: Path) -> ProcessArtifact:
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
    requires_python = project.get("requires-python")
    if not isinstance(project_name, str) or not project_name:
        raise DistributionError(f"Project name is invalid: {root / 'pyproject.toml'}")
    if not isinstance(project_version, str) or not project_version:
        raise DistributionError(
            f"Project version is invalid: {root / 'pyproject.toml'}"
        )
    if requires_python != f"=={PYTHON_VERSION}":
        raise DistributionError(
            f"Process artifact must require Python {PYTHON_VERSION}: {root / 'pyproject.toml'}"
        )
    command, system_profile, cpus, memory = _container_metadata(
        metadata,
        root / "pyproject.toml",
    )
    if root.name != command:
        raise DistributionError(
            f"Process artifact directory must match container command: {root}"
        )
    return ProcessArtifact(
        name=command,
        root=root,
        project_name=project_name,
        project_version=project_version,
        command=command,
        system_profile=system_profile,
        cpus=cpus,
        memory=memory,
    )


def _discover_artifacts(repository_root: Path) -> dict[str, ProcessArtifact]:
    artifacts_root = repository_root / "artifacts/processes"
    if not artifacts_root.is_dir():
        raise DistributionError(
            f"Process artifacts directory not found: {artifacts_root}. "
            "Prepare the required process artifacts before distributing them."
        )
    artifacts: dict[str, ProcessArtifact] = {}
    for pyproject_path in sorted(artifacts_root.glob("*/pyproject.toml")):
        artifact = _load_artifact(pyproject_path.parent)
        if artifact.name in artifacts:
            raise DistributionError(f"Duplicate process artifact: {artifact.name}")
        artifacts[artifact.name] = artifact
    if not artifacts:
        raise DistributionError(f"No process artifacts found: {artifacts_root}")
    return artifacts


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
    artifacts: dict[str, ProcessArtifact],
    selections: tuple[str, ...],
    targets: tuple[str, ...],
) -> tuple[ProcessArtifact, ...]:
    requested: list[str] = list(selections)
    for target in targets:
        requested.extend(_target_commands(repository_root, target))
    if not requested:
        raise DistributionError(
            "Select at least one process or provide one or more --target values"
        )
    unknown = tuple(name for name in dict.fromkeys(requested) if name not in artifacts)
    if unknown:
        raise DistributionError(
            "Prepared process artifact not found: " + ", ".join(unknown)
        )
    return tuple(artifacts[name] for name in dict.fromkeys(requested))


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
    process_name: str,
) -> None:
    current_process = current_root / "processes" / process_name
    for name in CONSUMER_CONFIGURATION_FILES:
        current = current_process / name
        if current.is_file():
            shutil.copy2(current, staged_process / name)


def _render_service(
    distribution_name: str,
    artifact: ProcessArtifact,
    *,
    volume_mode: str,
) -> str:
    volume_source = "runtime" if volume_mode == "named" else "./.runtime/volumen"
    return "\n".join(
        (
            f"  {artifact.name}:",
            f"    image: atlanticus-{distribution_name}-{artifact.name}:local",
            "    build:",
            "      context: .",
            "      dockerfile: Dockerfile",
            "      args:",
            f"        FILENAME: {artifact.name}",
            '    command: ["--run-once"]',
            '    restart: "no"',
            "    env_file:",
            f"      - ./processes/{artifact.name}/.env",
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
    artifacts: tuple[ProcessArtifact, ...],
    *,
    volume_mode: str,
) -> str:
    if volume_mode not in {"named", "bind"}:
        raise DistributionError(f"Unsupported volume mode: {volume_mode}")
    services = "\n".join(
        _render_service(distribution_name, artifact, volume_mode=volume_mode)
        for artifact in artifacts
    )
    volumes = "\nvolumes:\n  runtime:\n" if volume_mode == "named" else ""
    return (
        f"name: atlanticus-{distribution_name}-local\n"
        f'{DISTRIBUTION_CONTRACT_KEY}: "{DISTRIBUTION_CONTRACT_VERSION}"\n'
        f"services:\n{services}\n{volumes}"
    )


def _manifest(
    distribution_name: str,
    artifacts: tuple[ProcessArtifact, ...],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "name": distribution_name,
        "processes": [
            {
                "name": artifact.name,
                "project": artifact.project_name,
                "version": artifact.project_version,
                "system_profile": artifact.system_profile,
            }
            for artifact in artifacts
        ],
    }


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


def _validate_staging(
    *,
    staging_root: Path,
    distribution_name: str,
    artifacts: tuple[ProcessArtifact, ...],
) -> None:
    expected_names = tuple(artifact.name for artifact in artifacts)
    actual_names = tuple(
        sorted(
            path.name
            for path in (staging_root / "processes").iterdir()
            if path.is_dir()
        )
    )
    if actual_names != tuple(sorted(expected_names)):
        raise DistributionError(
            "Staged process set does not match the declared composition"
        )
    for artifact in artifacts:
        _load_artifact(staging_root / "processes" / artifact.name)
    manifest_path = staging_root / "distribution.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DistributionError(
            f"Generated distribution manifest is invalid: {manifest_path}"
        ) from error
    if manifest != _manifest(distribution_name, artifacts):
        raise DistributionError(
            "Generated distribution manifest does not match the selection"
        )
    for compose_name in ("compose.yaml", "compose.bind.yaml"):
        compose = (staging_root / compose_name).read_text(encoding="utf-8")
        marker = f'{DISTRIBUTION_CONTRACT_KEY}: "{DISTRIBUTION_CONTRACT_VERSION}"'
        if marker not in compose:
            raise DistributionError(
                f"Generated Compose contract is invalid: {compose_name}"
            )
        for process_name in expected_names:
            if f"  {process_name}:" not in compose:
                raise DistributionError(
                    f"Generated Compose is missing process {process_name}: {compose_name}"
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
) -> Path:
    if not DISTRIBUTION_NAME_PATTERN.fullmatch(distribution_name):
        raise DistributionError(f"Invalid distribution name: {distribution_name}")
    repository_root = repository_root.resolve()
    artifacts = _discover_artifacts(repository_root)
    selected = _resolve_selection(
        repository_root=repository_root,
        artifacts=artifacts,
        selections=selections,
        targets=targets,
    )
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    target_root = output_root / distribution_name
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{distribution_name}.atlanticus-", dir=output_root)
    )
    try:
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
        for artifact in selected:
            staged_process = processes_root / artifact.name
            shutil.copytree(
                artifact.root,
                staged_process,
                ignore=_artifact_ignore,
            )
            _preserve_consumer_configuration(
                target_root,
                staged_process,
                artifact.name,
            )
        (staging_root / "distribution.json").write_text(
            json.dumps(_manifest(distribution_name, selected), indent=2) + "\n",
            encoding="utf-8",
        )
        (staging_root / "compose.yaml").write_text(
            _render_compose(distribution_name, selected, volume_mode="named"),
            encoding="utf-8",
        )
        (staging_root / "compose.bind.yaml").write_text(
            _render_compose(distribution_name, selected, volume_mode="bind"),
            encoding="utf-8",
        )
        _copy_consumer_tooling(staging_root)
        _validate_staging(
            staging_root=staging_root,
            distribution_name=distribution_name,
            artifacts=selected,
        )
        _replace_directory(staging_root, target_root)
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    return target_root


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a declarative consumer distribution from prepared process artifacts."
    )
    parser.add_argument("distribution")
    parser.add_argument("processes", nargs="*")
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        help="Include every prepared process belonging to one logical source target.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        help="Output root. Defaults to distributed at the Atlanticus repository root.",
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
        else repository_root / "distributed"
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
    print(f"Configure process .env files under: {target / 'processes'}")
    print(f"Local validation: {target / 'tooling/local/processes/process.sh'} validate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
