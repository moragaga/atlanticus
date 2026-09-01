from __future__ import annotations

import ast
import importlib.util
import re
import sys
import tomllib
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "bundle.py"
SPEC = importlib.util.spec_from_file_location(
    "atlanticus_deployment_process_bundle", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
bundle = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bundle
SPEC.loader.exec_module(bundle)

ProcessBundleError = bundle.ProcessBundleError
build_process_bundle = bundle.build_process_bundle
discover_processes = bundle.discover_processes
discover_projects = bundle.discover_projects
load_project = bundle.load_project
resolve_internal_dependencies = bundle.resolve_internal_dependencies
resolve_process_root = bundle.resolve_process_root


def test_repository_root_matches_deployment_tooling_location() -> None:
    repository_root = bundle._repository_root_from_script()

    assert (
        repository_root / "deployment" / "processes" / "bundle.py"
    ).resolve() == MODULE_PATH.resolve()


def test_discovery_is_scope_neutral_and_can_be_filtered(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    operational = repository / "scopes" / "operational-data" / "processes" / "pi"
    command = repository / "scopes" / "ada-command" / "processes" / "alarms-runtime"
    _write_project(
        operational,
        name="atlanticus-operational-data-pi-process",
        command="operational-data-pi",
        system_profile="base",
    )
    _write_project(
        command,
        name="atlanticus-ada-command-alarms-runtime",
        command="ada-command-alarms-runtime",
        system_profile="base",
    )

    all_processes = discover_processes(repository)
    operational_only = discover_processes(repository, scope="operational-data")

    assert all_processes == (command, operational)
    assert operational_only == (operational,)


def test_named_resolution_accepts_container_command_and_rejects_ambiguity(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    operational = repository / "scopes" / "operational-data" / "processes" / "pi"
    other = repository / "scopes" / "other" / "processes" / "pi"
    _write_project(
        operational,
        name="atlanticus-operational-data-pi-process",
        command="operational-data-pi",
        system_profile="base",
    )
    _write_project(
        other,
        name="other-pi-process",
        command="other-pi",
        system_profile="base",
    )

    assert resolve_process_root(repository, "operational-data-pi") == operational
    assert (
        resolve_process_root(repository, "pi", scope="operational-data") == operational
    )
    with pytest.raises(ProcessBundleError, match="ambiguous process selection"):
        resolve_process_root(repository, "pi")


def test_container_command_must_be_safe_kebab_case(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    process = repository / "scopes" / "operational-data" / "processes" / "sample"
    _write_project(
        process,
        name="sample-process",
        command="Unsafe_Command",
        system_profile="base",
    )

    with pytest.raises(ProcessBundleError, match="container command is invalid"):
        bundle.load_container_definition(load_project(process))


def test_discover_projects_ignores_generated_runtime_and_artifacts(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    source = repository / "scopes" / "operational-data" / "processes" / "dispatch"
    runtime = repository / ".runtime" / "local-deployment" / "processes" / "dispatch"
    artifact = repository / "artifacts" / "processes" / "operational-data-dispatch"
    _write_project(
        source, name="sample-process", command="sample", system_profile="base"
    )
    _write_project(
        runtime, name="sample-process", command="sample", system_profile="base"
    )
    _write_project(
        artifact, name="sample-process", command="sample", system_profile="base"
    )

    projects = discover_projects(repository)

    assert projects["sample-process"].root == source


def test_internal_dependency_resolution_is_transitive_and_requires_exact_pins(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    process = repository / "scopes" / "operational-data" / "processes" / "sample"
    dependency_a = repository / "backend" / "dependency-a"
    dependency_b = repository / "backend" / "dependency-b"
    _write_project(
        process,
        name="sample-process",
        dependencies=("atlanticus-dependency-a==1.0.0", "pandas==3.0.3"),
        command="operational-data-sample",
        system_profile="base",
    )
    _write_project(
        dependency_a,
        name="atlanticus-dependency-a",
        dependencies=("atlanticus-dependency-b==1.0.0",),
    )
    _write_project(dependency_b, name="atlanticus-dependency-b")

    dependencies = resolve_internal_dependencies(
        load_project(process), discover_projects(repository)
    )

    assert tuple(item.name for item in dependencies) == (
        "atlanticus-dependency-b",
        "atlanticus-dependency-a",
    )

    _write_project(
        process,
        name="sample-process",
        dependencies=("atlanticus-dependency-a>=1.0.0",),
        command="operational-data-sample",
        system_profile="base",
    )
    with pytest.raises(ProcessBundleError, match="must be pinned exactly"):
        resolve_internal_dependencies(
            load_project(process), discover_projects(repository)
        )


def test_bundle_uses_container_command_as_artifact_identity_and_excludes_local_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    process = repository / "scopes" / "operational-data" / "processes" / "pi"
    dependency = repository / "backend" / "dependency"
    _write_project(
        process,
        name="atlanticus-operational-data-pi-process",
        dependencies=("atlanticus-dependency==1.0.0",),
        command="operational-data-pi",
        system_profile="base",
    )
    _write_project(dependency, name="atlanticus-dependency")
    (process / ".env").write_text("SECRET=must-not-travel\n", encoding="utf-8")
    (process / ".env.detail").write_text("ENVIRONMENT=local\n", encoding="utf-8")
    (process / "config.detail.json").write_text("{}\n", encoding="utf-8")
    (process / "secrets.detail.json").write_text("[]\n", encoding="utf-8")
    (process / "src" / "sample").mkdir(parents=True)
    (process / "src" / "sample" / "__init__.py").write_text("", encoding="utf-8")
    (process / "tests").mkdir()
    (process / "tests" / "test_sample.py").write_text(
        "def test_sample():\n    assert True\n", encoding="utf-8"
    )
    (process / "commented").mkdir()
    (process / "commented" / "sample.py").write_text("value = 1\n", encoding="utf-8")

    def fake_run(command: tuple[str, ...], *, cwd: Path) -> None:
        if command[:2] == ("uv", "build"):
            project = load_project(Path(command[2]))
            output = Path(command[command.index("--out-dir") + 1])
            output.mkdir(parents=True, exist_ok=True)
            wheel_name = re.sub(r"[-.]+", "_", project.name)
            (output / f"{wheel_name}-{project.version}-py3-none-any.whl").write_bytes(
                b"wheel"
            )
            return
        if command[:2] == ("uv", "lock"):
            (cwd / "uv.lock").write_text("version = 1\n", encoding="utf-8")
            return
        if command[:2] == ("uv", "sync"):
            command_path = cwd / ".venv" / "bin" / "operational-data-pi"
            command_path.parent.mkdir(parents=True)
            command_path.write_text("", encoding="utf-8")
            return
        if command[:2] == ("uv", "run"):
            return
        raise AssertionError(command)

    monkeypatch.setattr(bundle, "_run", fake_run)

    result = build_process_bundle(
        repository_root=repository,
        process_root=process,
        output_root=repository / "artifacts" / "processes",
    )

    assert result == repository / "artifacts" / "processes" / "operational-data-pi"
    assert (result / "uv.lock").is_file()
    assert (result / ".env.detail").is_file()
    assert (result / "config.detail.json").is_file()
    assert (result / "secrets.detail.json").is_file()
    assert not (result / ".env").exists()
    assert not (result / "tests").exists()
    assert not (result / "commented").exists()
    assert not (result / ".venv").exists()
    exported = tomllib.loads((result / "pyproject.toml").read_text(encoding="utf-8"))
    assert exported["tool"]["uv"]["default-groups"] == []
    assert exported["tool"]["uv"]["sources"]["atlanticus-dependency"][
        "path"
    ].startswith("wheels/")


def test_bundle_validation_is_transport_focused_and_does_not_replay_source_tests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[tuple[str, ...]] = []

    def capture(command: tuple[str, ...], *, cwd: Path) -> None:
        assert cwd == tmp_path
        commands.append(command)

    monkeypatch.setattr(bundle, "_run", capture)

    bundle._validate_bundle_project(tmp_path)

    assert ("uv", "lock", "--check") in commands
    assert (
        "uv",
        "run",
        "--python",
        bundle.PYTHON_VERSION,
        "--no-sync",
        "ruff",
        "check",
        "src",
    ) in commands
    assert (
        "uv",
        "run",
        "--python",
        bundle.PYTHON_VERSION,
        "--no-sync",
        "python",
        "-m",
        "compileall",
        "-q",
        "src",
    ) in commands
    assert not any("pytest" in command for command in commands)
    assert not any("tests" in command for command in commands)


def test_commented_bundle_is_structurally_equivalent() -> None:
    root = Path(__file__).resolve().parents[1]
    production = ast.dump(
        ast.parse((root / "bundle.py").read_text(encoding="utf-8")),
        include_attributes=False,
    )
    commented = ast.dump(
        ast.parse((root / "commented" / "bundle.py").read_text(encoding="utf-8")),
        include_attributes=False,
    )

    assert production == commented


def _write_project(
    root: Path,
    *,
    name: str,
    dependencies: tuple[str, ...] = (),
    command: str | None = None,
    system_profile: str | None = None,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    dependency_lines = "".join(f'    "{item}",\n' for item in dependencies)
    script_section = ""
    container_section = ""
    if command is not None:
        script_section = f'\n[project.scripts]\n{command} = "sample:main"\n'
        container_section = (
            "\n[tool.atlanticus.container]\n"
            f'command = "{command}"\n'
            f'system-profile = "{system_profile}"\n'
        )
    (root / "pyproject.toml").write_text(
        "[build-system]\n"
        'requires = ["setuptools==83.0.0"]\n'
        'build-backend = "setuptools.build_meta"\n\n'
        "[project]\n"
        f'name = "{name}"\n'
        'version = "1.0.0"\n'
        'requires-python = "==3.14.2"\n'
        'classifiers = ["Private :: Do Not Upload"]\n'
        "dependencies = [\n"
        f"{dependency_lines}"
        "]\n"
        f"{script_section}"
        f"{container_section}",
        encoding="utf-8",
    )
