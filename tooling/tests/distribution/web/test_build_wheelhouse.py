from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from packaging.tags import sys_tags

_TOOL = Path(__file__).resolve().parents[3] / "distribution/web/build_wheelhouse.py"
_spec = importlib.util.spec_from_file_location("build_web_wheelhouse", _TOOL)
assert _spec is not None and _spec.loader is not None
_tool = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _tool
_spec.loader.exec_module(_tool)


def _package(
    name: str = "example",
    version: str = "1.0",
    *,
    data: bytes = b"example",
    with_sdist: bool = False,
) -> dict:
    filename = f"{name}-{version}-py3-none-any.whl"
    package = {
        "name": name,
        "version": version,
        "wheels": [
            {
                "name": filename,
                "url": f"https://packages.example.invalid/{filename}",
                "hashes": {"sha256": hashlib.sha256(data).hexdigest()},
                "size": len(data),
            }
        ],
    }
    if with_sdist:
        source = f"{name}-{version}.tar.gz"
        package["sdist"] = {
            "name": source,
            "url": f"https://packages.example.invalid/{source}",
            "hashes": {"sha256": hashlib.sha256(b"source").hexdigest()},
            "size": len(b"source"),
        }
    return package


def test_compatible_wheels_are_selected_from_locked_sha256() -> None:
    supported = {tag: rank for rank, tag in enumerate(sys_tags())}
    filename, url, digest, size = _tool._choose_wheel(_package(), supported)
    assert filename == "example-1.0-py3-none-any.whl"
    assert url.endswith(filename)
    assert digest == hashlib.sha256(b"example").hexdigest()
    assert size == len(b"example")


def test_locked_sdist_is_fallback_when_platform_has_no_compatible_wheel() -> None:
    supported = {tag: rank for rank, tag in enumerate(sys_tags())}
    package = _package(with_sdist=True)
    package["wheels"][0]["name"] = "example-1.0-cp39-cp39-win_amd64.whl"

    kind, filename, url, digest, size = _tool._choose_registry_artifact(
        package, supported
    )

    assert kind == "sdist"
    assert filename == "example-1.0.tar.gz"
    assert url.endswith(filename)
    assert digest == hashlib.sha256(b"source").hexdigest()
    assert size == len(b"source")


def test_unlocked_or_unavailable_registry_artifact_is_rejected() -> None:
    supported = {tag: rank for rank, tag in enumerate(sys_tags())}
    unlocked = _package()
    unlocked["wheels"][0]["hashes"].clear()
    with pytest.raises(_tool.WheelhouseBuildError, match="No SHA256-locked compatible"):
        _tool._choose_registry_artifact(unlocked, supported)

    incompatible = _package()
    incompatible["wheels"][0]["name"] = "example-1.0-cp39-cp39-win_amd64.whl"
    with pytest.raises(_tool.WheelhouseBuildError, match="No SHA256-locked compatible"):
        _tool._choose_registry_artifact(incompatible, supported)


def test_build_constraints_include_exact_versions_and_locked_hashes(tmp_path) -> None:
    package = _package(name="setuptools", version="83.0.0", with_sdist=True)
    path = _tool._write_build_constraints(
        {"packages": [package]},
        tmp_path / "constraints.txt",
    )

    content = path.read_text()
    assert content.startswith("setuptools==83.0.0 ")
    assert f"--hash=sha256:{hashlib.sha256(b'example').hexdigest()}" in content
    assert f"--hash=sha256:{hashlib.sha256(b'source').hexdigest()}" in content


def test_locked_sdist_build_uses_hash_constrained_build_environment(
    tmp_path, monkeypatch
) -> None:
    archive = tmp_path / "example-1.0.tar.gz"
    archive.write_bytes(b"source")
    source = tmp_path / "source"
    source.mkdir()
    (source / "pyproject.toml").write_text(
        '[build-system]\nrequires=["setuptools"]\nbuild-backend="setuptools.build_meta"\n'
        '[project]\nname="example"\nversion="1.0"\n'
    )
    target = tmp_path / "wheelhouse"
    target.mkdir()
    constraints = tmp_path / "constraints.txt"
    constraints.write_text("setuptools==83.0.0 --hash=sha256:" + "a" * 64 + "\n")

    monkeypatch.setattr(_tool, "_extract_sdist", lambda *_args: source)

    def run(command, *, cwd):
        assert "--build-constraint" in command
        assert command[command.index("--build-constraint") + 1] == str(constraints)
        assert "--require-hashes" in command
        assert "--no-sources" in command
        assert cwd == _tool.REPOSITORY_ROOT
        (target / "example-1.0-py3-none-any.whl").write_bytes(b"wheel")

    monkeypatch.setattr(_tool, "_run", run)

    filename = _tool._build_locked_sdist(
        "uv",
        archive,
        tmp_path / "staging",
        target,
        constraints,
        "example",
        "1.0",
    )

    assert filename == "example-1.0-py3-none-any.whl"


def test_runtime_lock_rejects_ambiguous_versions_and_unresolved_extras() -> None:
    with pytest.raises(_tool.WheelhouseBuildError, match="Ambiguous"):
        _tool._active_packages({"packages": [_package(), _package(version="2.0")]})
    with pytest.raises(_tool.WheelhouseBuildError, match="extra markers"):
        _tool._active_packages(
            {"packages": [{**_package(), "marker": 'extra == "web"'}]}
        )


def test_local_source_requires_matching_package_inside_repository(tmp_path) -> None:
    repo = tmp_path / "repo"
    project = repo / "web"
    library = repo / "web/framework/core"
    library.mkdir(parents=True)
    (library / "pyproject.toml").write_text(
        '[project]\nname="atlanticus-web"\nversion="0.1.0"\n'
        'requires-python="==3.14.2"\n',
        encoding="utf-8",
    )
    package = {"name": "atlanticus-web", "directory": {"path": "framework/core"}}
    assert _tool._local_directory(package, project, repo) == library
    with pytest.raises(_tool.WheelhouseBuildError, match="outside repository"):
        _tool._local_directory(
            {"name": "atlanticus-web", "directory": {"path": "../../../elsewhere"}},
            project,
            repo,
        )


def _fixture(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    core = repo / "web/framework/core"
    core.mkdir(parents=True)
    (core / "pyproject.toml").write_text(
        '[build-system]\nrequires=["setuptools==83.0.0"]\n'
        '[project]\nname="atlanticus-web"\nversion="0.1.0"\n'
        'requires-python="==3.14.2"\n',
        encoding="utf-8",
    )
    app = tmp_path / "starter"
    app.mkdir()
    (app / "pyproject.toml").write_text(
        '[build-system]\nrequires=["setuptools==83.0.0"]\n'
        '[project]\nname="application-starter"\nversion="0.1.0"\n'
        'requires-python="==3.14.2"\n',
        encoding="utf-8",
    )
    content = (app / "pyproject.toml").read_bytes()
    (app / "manifest.json").write_text(
        json.dumps(
            {
                "artifact_kind": "web-application-starter",
                "profile": "generic",
                "wheelhouse_included": False,
                "files": {"pyproject.toml": hashlib.sha256(content).hexdigest()},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(_tool, "REPOSITORY_ROOT", repo)
    monkeypatch.setattr(_tool, "_require_python", lambda: None)

    def export(_uv, _project, _package, dest):
        assert dest.name == "pylock.runtime.toml"
        dest.write_text('lock-version="1.0"\n', encoding="utf-8")
        return {
            "lock-version": "1.0",
            "packages": [
                {"name": "atlanticus-web", "directory": {"path": "framework/core"}},
            ],
        }

    def build_requirements(_uv, requirements, _staging):
        assert requirements == ["setuptools==83.0.0"]
        return {
            "lock-version": "1.0",
            "packages": [
                _package(
                    name="setuptools",
                    version="83.0.0",
                    data=b"fake-setuptools",
                )
            ],
        }

    def build_internal(_uv, path, target, name, version):
        assert path == core
        assert name == "atlanticus-web" and version == "0.1.0"
        filename = "atlanticus_web-0.1.0-py3-none-any.whl"
        (target / filename).write_bytes(b"internal-wheel")
        return filename

    def download(_url, destination, sha, _size):
        assert hashlib.sha256(b"fake-setuptools").hexdigest() == sha
        destination.write_bytes(b"fake-setuptools")

    original_run = _tool.subprocess.run

    def fake_run(command, **kwargs):
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return SimpleNamespace(stdout="testcommit\n")
        return original_run(command, **kwargs)

    monkeypatch.setattr(_tool, "_export_runtime_lock", export)
    monkeypatch.setattr(_tool, "_lock_build_dependencies", build_requirements)
    monkeypatch.setattr(_tool, "_build_internal", build_internal)
    monkeypatch.setattr(_tool, "_download_locked_artifact", download)
    monkeypatch.setattr(_tool.subprocess, "run", fake_run)
    return app


def test_build_is_atomic_and_records_hashes_without_sources(
    tmp_path, monkeypatch
) -> None:
    app = _fixture(tmp_path, monkeypatch)
    result = _tool.build_wheelhouse(profile="generic", application=app, uv="uv")
    assert result["status"] == "BUILT_UNQUALIFIED"
    assert result["packages"] == 2
    assert (
        json.loads((app / "manifest.json").read_text())["wheelhouse_included"] is True
    )
    wheelhouse = app / "wheelhouse"
    metadata = json.loads((wheelhouse / "manifest.json").read_text())
    assert metadata["source_git_head"] == "testcommit"
    assert {entry["name"] for entry in metadata["packages"]} == {
        "atlanticus-web",
        "setuptools",
    }
    for entry in metadata["packages"]:
        assert _tool._sha256(wheelhouse / entry["filename"]) == entry["sha256"]
    assert not list(app.glob(".wheelhouse-*"))
    with pytest.raises(_tool.WheelhouseBuildError, match="regenerated"):
        _tool.build_wheelhouse(profile="generic", application=app, uv="uv")


def test_download_failure_leaves_starter_unchanged(tmp_path, monkeypatch) -> None:
    app = _fixture(tmp_path, monkeypatch)
    source = (app / "manifest.json").read_bytes()

    def fail(*_args):
        raise _tool.WheelhouseBuildError("Network failure")

    monkeypatch.setattr(_tool, "_download_locked_artifact", fail)
    with pytest.raises(_tool.WheelhouseBuildError, match="Network failure"):
        _tool.build_wheelhouse(profile="generic", application=app, uv="uv")
    assert not (app / "wheelhouse").exists()
    assert (app / "manifest.json").read_bytes() == source




@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is required")
def test_uv_accepts_runtime_and_build_pylock_paths(tmp_path, monkeypatch) -> None:
    uv = shutil.which("uv")
    project = tmp_path / "project"
    project.mkdir()
    version = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    (project / "pyproject.toml").write_text(
        "[build-system]\n"
        'requires = ["setuptools==83.0.0"]\n'
        'build-backend = "setuptools.build_meta"\n'
        "[project]\n"
        'name = "pylock-smoke"\n'
        'version = "0.1.0"\n'
        f'requires-python = "=={version}"\n'
        "dependencies = []\n",
        encoding="utf-8",
    )
    environment = dict(__import__("os").environ, UV_OFFLINE="1")
    subprocess.run(
        [uv, "lock", "--project", str(project), "--python", sys.executable],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    monkeypatch.setenv("UV_OFFLINE", "1")
    runtime = _tool._export_runtime_lock(
        uv,
        project,
        None,
        tmp_path / "pylock.runtime.toml",
    )
    empty = tmp_path / "empty.in"
    empty.write_text("", encoding="utf-8")
    subprocess.run(
        [
            uv,
            "pip",
            "compile",
            str(empty),
            "--python",
            sys.executable,
            "--no-sources",
            "--format",
            "pylock.toml",
            "--output-file",
            str(tmp_path / "pylock.build.toml"),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert runtime["lock-version"] == "1.0"
    assert _tool._read_toml(tmp_path / "pylock.build.toml")["lock-version"] == "1.0"
    assert (tmp_path / "pylock.runtime.toml").is_file()
    assert (tmp_path / "pylock.build.toml").is_file()


def test_build_dependency_compiler_receives_valid_pylock_filename(
    tmp_path, monkeypatch
) -> None:
    def fake_run(command, *, cwd):
        assert command[1:3] == ["pip", "compile"]
        output = Path(command[command.index("--output-file") + 1])
        assert output.name == "pylock.build.toml"
        output.write_text(
            'lock-version = "1.0"\n[[packages]]\nname="setuptools"\nversion="83.0.0"\n',
            encoding="utf-8",
        )

    monkeypatch.setattr(_tool, "_run", fake_run)
    result = _tool._lock_build_dependencies("uv", ["setuptools==83.0.0"], tmp_path)
    assert result["packages"][0]["name"] == "setuptools"
