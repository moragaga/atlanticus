from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "generate_compose.py"
SPEC = importlib.util.spec_from_file_location(
    "atlanticus_local_deployment", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
local_deployment = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = local_deployment
SPEC.loader.exec_module(local_deployment)

DEFAULT_CPUS = local_deployment.DEFAULT_CPUS
DEFAULT_MEMORY = local_deployment.DEFAULT_MEMORY
LocalDeploymentError = local_deployment.LocalDeploymentError
discover_processes = local_deployment.discover_processes
prepare_workspace = local_deployment.prepare_workspace
validate_environment_files = local_deployment.validate_environment_files
validate_source_contracts = local_deployment.validate_source_contracts
validate_workspace_contract = local_deployment.validate_workspace_contract


def test_discovery_uses_artifact_identity_and_resource_defaults(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _write_artifact(repository, "operational-data-dispatch", profile="sqlserver")

    definition = discover_processes(repository)[0]

    assert definition.name == "operational-data-dispatch"
    assert definition.command == "operational-data-dispatch"
    assert definition.system_profile == "sqlserver"
    assert definition.cpus == DEFAULT_CPUS
    assert definition.memory == DEFAULT_MEMORY
    assert (
        definition.env_file
        == repository / "artifacts/processes/operational-data-dispatch/.env"
    )


def test_environment_file_is_required_outside_transport_payload(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _write_artifact(repository, "operational-data-pi", profile="base", env=False)

    with pytest.raises(LocalDeploymentError, match=r"operational-data-pi/\.env"):
        validate_environment_files(discover_processes(repository))


def test_source_contract_validation_accepts_current_artifact(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _write_source_process(
        repository,
        "ada",
        "kpi-runtime",
        command="ada-kpi-runtime",
        project_name="ada-kpi-runtime-process",
        version="1.0.1",
        backend=True,
    )
    _write_artifact(
        repository,
        "ada-kpi-runtime",
        profile="base",
        project_name="ada-kpi-runtime-process",
        version="1.0.1",
    )

    validate_source_contracts(repository, discover_processes(repository))


def test_source_contract_validation_rejects_stale_artifact_with_actionable_message(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    _write_source_process(
        repository,
        "ada",
        "kpi-runtime",
        command="ada-kpi-runtime",
        project_name="ada-kpi-runtime-process",
        version="1.0.1",
        backend=True,
    )
    _write_artifact(
        repository,
        "ada-kpi-runtime",
        profile="base",
        project_name="ada-kpi-runtime-process",
        version="1.0.0",
    )

    with pytest.raises(
        LocalDeploymentError,
        match=r"artifact contract is stale.*source ada-kpi-runtime-process==1\.0\.1"
        r".*artifact ada-kpi-runtime-process==1\.0\.0"
        r".*prepare ada-kpi-runtime",
    ):
        validate_source_contracts(repository, discover_processes(repository))


def test_workspace_excludes_active_configuration_and_generates_run_once_services(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    artifact = _write_artifact(repository, "operational-data-pi", profile="base")
    (artifact / "config.json").write_text('{"active": true}\n', encoding="utf-8")
    (artifact / "secrets.json").write_text('[{"secret": "active"}]\n', encoding="utf-8")
    workspace = repository / ".runtime" / "local-deployment"

    compose_path = prepare_workspace(
        repository_root=repository,
        workspace_root=workspace,
        definitions=discover_processes(repository),
        volume_mode="named",
    )

    compose = compose_path.read_text(encoding="utf-8")
    assert "name: atlanticus-processes-local" in compose
    assert 'x-atlanticus-local-contract: "2"' in compose
    assert "FILENAME: operational-data-pi" in compose
    assert "../../artifacts/processes/operational-data-pi/.env" in compose
    assert 'command: ["--run-once"]' in compose
    assert 'restart: "no"' in compose
    assert "VOLUMEN_PATH: /app/volumen" in compose
    assert "runtime:/app/volumen" in compose
    copied = workspace / "processes" / "operational-data-pi"
    assert (copied / "pyproject.toml").is_file()
    assert not (copied / ".env").exists()
    assert not (copied / "config.json").exists()
    assert not (copied / "secrets.json").exists()
    validate_workspace_contract(workspace)


def test_legacy_workspace_contract_is_rejected_with_rebuild_instruction(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "compose.yaml").write_text(
        "name: atlanticus-processes-local\n"
        "services:\n"
        "  sample:\n"
        "    environment:\n"
        "      VOLUMEN_PATH: /app/volume\n"
        "    volumes:\n"
        "      - runtime:/app/volume\n",
        encoding="utf-8",
    )

    with pytest.raises(
        LocalDeploymentError,
        match=r"workspace contract is stale.*legacy volume path /app/volume.*local-process\.sh build",
    ):
        validate_workspace_contract(workspace)


def test_bind_workspace_preserves_runtime_directory(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _write_artifact(repository, "operational-data-remanentes", profile="base")
    workspace = repository / ".runtime" / "local-deployment"
    runtime = workspace / "runtime"
    runtime.mkdir(parents=True)
    marker = runtime / "state.keep"
    marker.write_text("state", encoding="utf-8")

    compose = prepare_workspace(
        repository_root=repository,
        workspace_root=workspace,
        definitions=discover_processes(repository),
        volume_mode="bind",
    ).read_text(encoding="utf-8")

    assert "./runtime:/app/volumen" in compose
    assert "\nvolumes:\n" not in compose
    assert marker.read_text(encoding="utf-8") == "state"


def test_commented_generator_is_structurally_equivalent() -> None:
    root = Path(__file__).resolve().parents[1]
    production = ast.dump(
        ast.parse((root / "generate_compose.py").read_text(encoding="utf-8")),
        include_attributes=False,
    )
    commented = ast.dump(
        ast.parse(
            (root / "commented" / "generate_compose.py").read_text(encoding="utf-8")
        ),
        include_attributes=False,
    )
    assert production == commented


def test_docker_context_is_allowlisted_to_transport_files() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    dockerignore = (repository_root / "deployment/processes/.dockerignore").read_text(
        encoding="utf-8"
    )
    dockerfile = (repository_root / "deployment/processes/Dockerfile").read_text(
        encoding="utf-8"
    )

    assert "!processes/*/pyproject.toml" in dockerignore
    assert "!processes/*/uv.lock" in dockerignore
    assert "!processes/*/wheels/**" in dockerignore
    assert "!processes/*/src/**" in dockerignore
    assert "!processes/**" not in dockerignore
    assert "COPY processes/${FILENAME}/ ./" not in dockerfile
    assert "COPY processes/${FILENAME}/src ./src" in dockerfile
    assert "config.json" not in dockerfile
    assert "secrets.json" not in dockerfile


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    docker_root = repository / "deployment" / "processes"
    docker_root.mkdir(parents=True)
    (docker_root / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (docker_root / ".dockerignore").write_text("*\n", encoding="utf-8")
    return repository


def _write_source_process(
    repository: Path,
    scope: str,
    directory: str,
    *,
    command: str,
    project_name: str,
    version: str,
    backend: bool,
) -> Path:
    root = repository / "scopes" / scope
    if backend:
        root = root / "backend"
    root = root / "processes" / directory
    root.mkdir(parents=True)
    _write_pyproject(
        root / "pyproject.toml",
        command=command,
        profile="base",
        project_name=project_name,
        version=version,
    )
    return root


def _write_artifact(
    repository: Path,
    name: str,
    *,
    profile: str,
    env: bool = True,
    project_name: str | None = None,
    version: str = "1.0.0",
) -> Path:
    root = repository / "artifacts" / "processes" / name
    root.mkdir(parents=True)
    _write_pyproject(
        root / "pyproject.toml",
        command=name,
        profile=profile,
        project_name=project_name or f"{name}-process",
        version=version,
    )
    (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (root / "wheels").mkdir()
    (root / "src").mkdir()
    if env:
        (root / ".env").write_text("ENVIRONMENT=local\n", encoding="utf-8")
    return root


def _write_pyproject(
    path: Path,
    *,
    command: str,
    profile: str,
    project_name: str,
    version: str,
) -> None:
    path.write_text(
        "[project]\n"
        f'name = "{project_name}"\n'
        f'version = "{version}"\n'
        'requires-python = "==3.14.2"\n'
        'dependencies = ["sample-dependency==1.0.0"]\n\n'
        "[project.scripts]\n"
        f'{command} = "sample:main"\n\n'
        "[tool.atlanticus.container]\n"
        f'command = "{command}"\n'
        f'system-profile = "{profile}"\n',
        encoding="utf-8",
    )
