from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import tomllib
from pathlib import Path

import pytest

_ROOT = (
    Path(__file__).resolve().parents[5] / "scopes/ada/tooling/distribution/web/starter"
)
_TOOL = _ROOT / "tooling/project.py"
_SPEC = importlib.util.spec_from_file_location(
    "ada_distributed_project_tool_for_tests", _TOOL
)
assert _SPEC is not None and _SPEC.loader is not None
project = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(project)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hashed(name: str) -> str:
    return f"{name}==1.0.0 \\\n    --hash=sha256:{hashlib.sha256(name.encode()).hexdigest()}\n"


@pytest.fixture
def distribution(tmp_path, monkeypatch):
    root = tmp_path / "ada"
    (root / "requirements").mkdir(parents=True)
    (root / "wheelhouse").mkdir()
    (root / "src").mkdir()
    (root / "src/application").mkdir()
    (root / "src/application/__main__.py").write_text('print("ready")\n')
    (root / ".env.detail").write_text("ATLANTICUS_ENVIRONMENT=local\n")
    (root / "pyproject.toml").write_text(
        '[project]\nname="ada-application-starter"\nversion="0.1.0"\n'
        'dependencies = [\n    "ada-generic-application==0.2.17",\n]\n'
        '[tool.custom]\nmessage="keep-me"\n',
        encoding="utf-8",
    )
    wheel = root / "wheelhouse/ada_generic_application-0.2.17-py3-none-any.whl"
    wheel.write_bytes(b"wheel")
    req = root / "requirements"
    for name in ("external-runtime.txt", "host-runtime.txt", "starter-build.txt"):
        (req / name).write_text(
            hashed(name.replace("-runtime", "").replace(".txt", ""))
        )
    (req / "project-runtime.txt").write_bytes(
        (req / "external-runtime.txt").read_bytes()
    )
    wheel_manifest = {
        "schema_version": 2,
        "strategy": "internal-wheels-external-image-build",
        "python": project.PYTHON_VERSION,
        "packages": [
            {
                "name": "ada-generic-application",
                "version": "0.2.17",
                "filename": wheel.name,
                "sha256": sha(wheel),
            }
        ],
        "requirements": {
            name: sha(req / name)
            for name in (
                "external-runtime.txt",
                "host-runtime.txt",
                "starter-build.txt",
            )
        },
    }
    (root / "wheelhouse/manifest.json").write_text(json.dumps(wheel_manifest))
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "artifact_kind": "web-application-starter",
                "profile": "ada",
                "wheelhouse_included": True,
                "delivery_strategy": "internal-wheels-external-image-build",
                "files": {"pyproject.toml": sha(root / "pyproject.toml")},
            }
        )
    )
    (req / "project.lock.json").write_text(
        json.dumps(
            project._snapshot(
                root,
                (root / "pyproject.toml").read_bytes(),
                (req / "project-runtime.txt").read_bytes(),
            )
        )
    )
    monkeypatch.setattr(
        project.platform, "python_version", lambda: project.PYTHON_VERSION
    )
    monkeypatch.setattr(project.shutil, "which", lambda name: "/usr/bin/uv")
    return root


def test_unchanged_release_lock_is_accepted(distribution):
    result = project._locked(distribution)
    assert result["schema_version"] == 1
    assert (
        project._external_dependencies(
            distribution, project._read_project(distribution)[1]
        )
        == []
    )


def test_dependency_add_writes_pyproject_and_hashed_runtime_without_changing_base(
    distribution, monkeypatch
):
    base = (distribution / "requirements/external-runtime.txt").read_bytes()
    wheel = (
        distribution / "wheelhouse/ada_generic_application-0.2.17-py3-none-any.whl"
    ).read_bytes()
    commands = []

    def compile_runtime(command, *, root, **_kw):
        commands.append(command)
        assert command[1:3] == ["pip", "compile"]
        assert "--universal" in command
        assert command.count("--constraints") == 2
        assert "--generate-hashes" in command
        target = Path(command[command.index("--output-file") + 1])
        target.write_bytes(base + hashed("pandas").encode())

    monkeypatch.setattr(project, "_command", compile_runtime)
    result = project.resolve(distribution, new_dependency="pandas")
    assert result == {"status": "LOCKED", "additional_dependencies": 1}
    metadata = tomllib.loads((distribution / "pyproject.toml").read_text())
    assert metadata["project"]["dependencies"][-1] == "pandas"
    assert metadata["tool"]["custom"]["message"] == "keep-me"
    assert base == (distribution / "requirements/external-runtime.txt").read_bytes()
    assert (
        wheel
        == (
            distribution / "wheelhouse/ada_generic_application-0.2.17-py3-none-any.whl"
        ).read_bytes()
    )
    assert project._locked(distribution)["project_runtime_sha256"] == sha(
        distribution / "requirements/project-runtime.txt"
    )
    assert len(commands) == 1


def test_dependency_replacement_does_not_duplicate_declarations(
    distribution, monkeypatch
):
    def compile_runtime(command, *, root, **_kw):
        Path(command[command.index("--output-file") + 1]).write_text(hashed("external"))

    monkeypatch.setattr(project, "_command", compile_runtime)
    project.resolve(distribution, new_dependency="pandas==3.0.0")
    project.resolve(distribution, new_dependency="pandas==3.1.0")
    specs = project._read_project(distribution)[1]
    assert specs == ["ada-generic-application==0.2.17", "pandas==3.1.0"]


def test_failed_resolution_preserves_original_release_and_derived_lock(
    distribution, monkeypatch
):
    before = {
        name: (distribution / name).read_bytes()
        for name in (
            "pyproject.toml",
            "requirements/project-runtime.txt",
            "requirements/project.lock.json",
        )
    }

    def fail(command, *, root, **_kw):
        raise project.ProjectError("Dependency resolution conflict")

    monkeypatch.setattr(project, "_command", fail)
    with pytest.raises(project.ProjectError, match="resolution conflict"):
        project.resolve(distribution, new_dependency="other-package")
    assert before == {name: (distribution / name).read_bytes() for name in before}


def test_internal_dependency_cannot_be_replaced(distribution):
    with pytest.raises(project.ProjectError, match="Internal distribution package"):
        project.resolve(distribution, new_dependency="ada-generic-application==999.0.0")


def test_generated_project_lock_rejects_manual_changes_until_resolved(distribution):
    location = distribution / "pyproject.toml"
    location.write_text(location.read_text().replace("0.1.0", "0.2.0"))
    with pytest.raises(project.ProjectError, match="stale"):
        project._locked(distribution)
    assert project.resolve(distribution)["status"] == "LOCKED"
    project._locked(distribution)


def test_external_original_tampering_invalidates_lock(distribution):
    path = distribution / "requirements/external-runtime.txt"
    path.write_bytes(path.read_bytes() + b"tampered")
    with pytest.raises(project.ProjectError, match="stale"):
        project._locked(distribution)


def test_init_copies_template_only_on_request(distribution, monkeypatch):
    commands = []
    monkeypatch.setattr(
        project, "_command", lambda command, **_kw: commands.append(command)
    )
    response = project.init(distribution, no_sync=True)
    assert response == {
        "status": "LOCKED",
        "env_template_copied": False,
        "env_file_present": False,
        "env_placeholders": (),
    }
    response = project.init(distribution, copy_env=True, no_sync=True)
    assert response["env_template_copied"] is True
    assert response["env_placeholders"] == ()
    (distribution / ".env").write_text("CUSTOM=true\n")
    response = project.init(distribution, copy_env=True, no_sync=True)
    assert response["env_template_copied"] is False
    assert (distribution / ".env").read_text() == "CUSTOM=true\n"
    assert not commands


def _stub_sync_commands(monkeypatch, commands):
    def execute(command, *, root, **_kw):
        commands.append(command)
        if command[1] == "venv" and Path(command[2]) == root / ".venv":
            executable = project._python(root)
            executable.parent.mkdir(parents=True, exist_ok=True)
            executable.write_bytes(b"python")
        if command[1] == "build":
            output = Path(command[command.index("--out-dir") + 1])
            (output / "ada_application_starter-0.1.0-py3-none-any.whl").write_bytes(
                b"wheel"
            )

    monkeypatch.setattr(project, "_command", execute)


def test_sync_installs_hashed_runtime_and_internal_wheels_and_is_repeatable(
    distribution, monkeypatch
):
    commands = []
    _stub_sync_commands(monkeypatch, commands)
    output = project.sync(distribution)
    assert output["status"] == "SYNCED"
    assert len(commands) == 8
    assert "--require-hashes" in commands[1]
    assert "project-runtime.txt" in " ".join(commands[1])
    assert "--no-index" in commands[2]
    assert commands[3][1] == "venv"
    assert "--require-hashes" in commands[4]
    assert "starter-build.txt" in " ".join(commands[4])
    assert commands[5][1:4] == ["build", "--wheel", "--no-build-isolation"]
    assert "--no-index" in commands[6]
    assert "ada_application_starter-0.1.0" in commands[6][-1]
    assert commands[7][1:3] == ["pip", "check"]
    assert project.sync(distribution)["status"] == "ALREADY_SYNCED"
    assert len(commands) == 8
    project.sync(distribution, force=True)
    assert len(commands) == 16
    assert commands[8][1] == "venv"


def test_sync_rebuilds_starter_when_its_source_changes(distribution, monkeypatch):
    commands = []
    _stub_sync_commands(monkeypatch, commands)
    assert project.sync(distribution)["status"] == "SYNCED"
    assert project.sync(distribution)["status"] == "ALREADY_SYNCED"
    (distribution / "src/application/__main__.py").write_text('print("changed")\n')
    assert project.sync(distribution)["status"] == "SYNCED"
    assert len(commands) == 16


def test_failed_starter_build_does_not_leave_a_valid_sync_stamp(
    distribution, monkeypatch
):
    commands = []
    _stub_sync_commands(monkeypatch, commands)
    initial = project._command

    def failing(command, *, root, **kwargs):
        if command[1] == "build":
            raise project.ProjectError("Starter build failed")
        initial(command, root=root, **kwargs)

    monkeypatch.setattr(project, "_command", failing)
    with pytest.raises(project.ProjectError, match="Starter build failed"):
        project.sync(distribution)
    assert not (distribution / ".runtime/project-sync.json").exists()
    _stub_sync_commands(monkeypatch, commands)
    assert project.sync(distribution)["status"] == "SYNCED"
    assert project.sync(distribution)["status"] == "ALREADY_SYNCED"


def test_sync_does_not_install_on_stale_dependencies(distribution, monkeypatch):
    (distribution / "pyproject.toml").write_text(
        '[project]\nname="changed"\ndependencies=[]\n'
    )
    monkeypatch.setattr(
        project, "_command", lambda *_a, **_kw: pytest.fail("Should not run uv")
    )
    with pytest.raises(project.ProjectError, match="stale"):
        project.sync(distribution)


def test_run_executes_editable_source_without_activating_venv(
    distribution, monkeypatch
):
    env = {}
    monkeypatch.setattr(project, "sync", lambda root: {"status": "SYNCED"})

    def execute(command, *, root, environment=None, **_kw):
        env["command"] = command
        env["pythonpath"] = environment["PYTHONPATH"]

    monkeypatch.setattr(project, "_command", execute)
    project.run(distribution)
    assert env["command"][-2:] == ["-m", "application"]
    assert env["pythonpath"].split(os.pathsep)[0] == str(distribution / "src")


def test_local_run_rejects_unresolved_template(distribution, monkeypatch):
    (distribution / ".env").write_text("CONNECTION=<set-connection>\n")
    monkeypatch.setattr(project, "sync", lambda root: pytest.fail("Should not sync"))
    with pytest.raises(
        project.ProjectError, match="Unresolved environment placeholders: CONNECTION"
    ):
        project.run(distribution)


def test_local_run_rejects_production(distribution, monkeypatch):
    monkeypatch.delenv("ATLANTICUS_ENVIRONMENT", raising=False)
    (distribution / ".env").write_text("ATLANTICUS_ENVIRONMENT=production\n")
    monkeypatch.setattr(project, "sync", lambda root: pytest.fail("Should not sync"))
    with pytest.raises(project.ProjectError, match="production"):
        project.run(distribution)


def test_docker_build_uses_distributed_context_with_derived_lock(
    distribution, monkeypatch
):
    commands = []
    monkeypatch.setattr(
        project, "_command", lambda command, **_kw: commands.append(command)
    )
    project.docker(distribution, "build", tag="custom:demo")
    assert commands == [["docker", "build", "--tag", "custom:demo", str(distribution)]]


def test_compose_profile_requires_generated_files_and_env(distribution, monkeypatch):
    for key in ("ADA_TOOL_NAMESPACE", "ADA_COSMOS_VOLUME", "ADA_AZURITE_VOLUME"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(project.ProjectError, match="not generated"):
        project.compose(distribution, "up", "full")
    directory = distribution / "deployment/compose"
    directory.mkdir(parents=True)
    (directory / "full.yaml").write_text("services: {}\n")
    with pytest.raises(project.ProjectError, match="configured .env"):
        project.compose(distribution, "up", "full")
    (distribution / ".env").write_text("EXAMPLE=1\n")
    with pytest.raises(project.ProjectError, match="ADA_TOOL_NAMESPACE"):
        project.compose(distribution, "up", "full")
    (distribution / ".env").write_text("ADA_TOOL_NAMESPACE=operaciones_integradas\n")
    commands = []
    monkeypatch.setattr(project, "_running_compose_project", lambda *_args: False)
    monkeypatch.setattr(project, "_docker_network", lambda *_args, **_kw: None)
    monkeypatch.setattr(
        project, "_command", lambda command, **_kw: commands.append(command)
    )
    project.compose(distribution, "up", "full")
    assert commands[:2] == [
        ["docker", "volume", "create", "ada-generic-cosmos"],
        ["docker", "volume", "create", "ada-generic-azurite"],
    ]
    assert commands[2][-2:] == ["up", "--detach"]
    assert str(directory / "full.yaml") in commands[2]




def test_unhashed_resolver_output_is_rejected_before_mutating_project(
    distribution, monkeypatch
):
    original = (distribution / "pyproject.toml").read_bytes()

    def invalid(command, *, root, **_kw):
        Path(command[command.index("--output-file") + 1]).write_text("pandas==3.0.0\n")

    monkeypatch.setattr(project, "_command", invalid)
    with pytest.raises(project.ProjectError, match="unhashed"):
        project.resolve(distribution, new_dependency="pandas")
    assert (distribution / "pyproject.toml").read_bytes() == original


def test_deployed_tool_rejects_modified_original_wheel(distribution):
    (
        distribution / "wheelhouse/ada_generic_application-0.2.17-py3-none-any.whl"
    ).write_bytes(b"tampered-wheel")
    with pytest.raises(project.ProjectError, match="internal wheel was changed"):
        project.init(distribution, no_sync=True)


@pytest.mark.skipif(project.shutil.which("uv") is None, reason="uv is required")
def test_real_uv_compiles_universal_hash_lock_from_frozen_requirements_offline(
    tmp_path,
    monkeypatch,
):
    import zipfile

    local = tmp_path / "packages"
    local.mkdir()

    def wheel(name, version, dependencies=()):
        stem = name.replace("-", "_")
        output = local / f"{stem}-{version}-py3-none-any.whl"
        metadata = (
            f"Metadata-Version: 2.3\nName: {name}\nVersion: {version}\n"
            "Requires-Python: >=3.11\n"
            + "".join(f"Requires-Dist: {item}\n" for item in dependencies)
        )
        prefix = f"{stem}-{version}.dist-info"
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr(f"{prefix}/METADATA", metadata)
            archive.writestr(
                f"{prefix}/WHEEL",
                "Wheel-Version: 1.0\nGenerator: fixture\nRoot-Is-Purelib: true\n"
                "Tag: py3-none-any\n",
            )
            archive.writestr(f"{prefix}/RECORD", "")
        return output

    base = wheel("sample-base", "1.0.0")
    host = wheel("sample-host", "1.0.0")
    wheel("sample-extra", "2.0.0", ("sample-base==1.0.0",))
    requirements = tmp_path / "requirements"
    requirements.mkdir()
    for filename, package in (
        ("external-runtime.txt", base),
        ("host-runtime.txt", host),
    ):
        name = package.name.split("-")[0].replace("_", "-")
        (requirements / filename).write_text(
            f"{name}==1.0.0 \\\n    --hash=sha256:{sha(package)}\n",
            encoding="utf-8",
        )
    monkeypatch.setenv("UV_FIND_LINKS", str(local))
    monkeypatch.setenv("UV_NO_INDEX", "1")
    monkeypatch.setenv("UV_OFFLINE", "1")
    output = project._compile(
        tmp_path,
        ["sample-extra"],
        tmp_path / "resolved.txt",
        project.shutil.which("uv"),
    )
    contents = output.decode("utf-8")
    assert "sample-base==1.0.0" in contents
    assert "sample-extra==2.0.0" in contents
    assert "--hash=sha256:" in contents
    assert "sample-host" not in contents


def test_signed_but_unhashed_mutable_lock_is_not_accepted(distribution):
    requirements = distribution / "requirements"
    (requirements / "project-runtime.txt").write_text("unhashed==1.0.0\n")
    project_bytes = (distribution / "pyproject.toml").read_bytes()
    runtime = (requirements / "project-runtime.txt").read_bytes()
    (requirements / "project.lock.json").write_text(
        json.dumps(project._snapshot(distribution, project_bytes, runtime))
    )
    with pytest.raises(project.ProjectError, match="unhashed"):
        project._locked(distribution)


def test_web_compose_validates_current_durable_contract(distribution, monkeypatch):
    directory = distribution / "deployment/compose"
    directory.mkdir(parents=True)
    (directory / "web.yaml").write_text("services: {}\n")
    monkeypatch.setattr(project, "_docker_network", lambda *_args, **_kw: None)
    monkeypatch.setattr(project, "_command", lambda *_args, **_kw: None)

    (distribution / ".env").write_text(
        "ADA_PERSISTENCE_MODE=local\nADA_TOOL_NAMESPACE=operaciones_integradas\n"
    )
    with pytest.raises(project.ProjectError, match="ADA_PERSISTENCE_MODE=durable"):
        project.compose(distribution, "up", "web")

    (distribution / ".env").write_text(
        "ADA_PERSISTENCE_MODE=durable\nADA_TOOL_NAMESPACE=<tool-namespace>\n"
    )
    with pytest.raises(project.ProjectError, match="ADA_TOOL_NAMESPACE"):
        project.compose(distribution, "up", "web")

    (distribution / ".env").write_text(
        "ADA_PERSISTENCE_MODE=durable\n"
        "ADA_TOOL_NAMESPACE=operaciones_integradas\n"
        "ADA_STORAGE_CONTAINER_NAME=dataproduct\n"
        "ADA_STORAGE_CONNECTION_STRING=UseDevelopmentStorage=true\n"
        "ADA_COSMOS_ENDPOINT=http://cosmos-emulator:8081\n"
        "ADA_COSMOS_KEY=test-key\n"
        "ADA_COSMOS_DATABASE_NAME=ada-local\n"
    )
    project.compose(distribution, "up", "web")
