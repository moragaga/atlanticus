from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import platform
import sys
from pathlib import Path

import pytest

_REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
_ROOT = (
    Path(__file__).resolve().parents[5] / "scopes/ada/tooling/distribution/web/starter"
)
_GENERATOR = _REPOSITORY_ROOT / "tooling/distribution/web/generate_starter.py"
_VERIFY = _ROOT / "docker/verify_delivery.py"
_spec = importlib.util.spec_from_file_location("verify_ada_delivery_for_tests", _VERIFY)
assert _spec is not None and _spec.loader is not None
_verifier = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_verifier)


def _candidate(tmp_path):
    root = tmp_path / "ada"
    wheelhouse = root / "wheelhouse"
    requirements = root / "requirements"
    wheelhouse.mkdir(parents=True)
    requirements.mkdir()
    wheel = wheelhouse / "ada_generic_application-0.2.17-py3-none-any.whl"
    wheel.write_bytes(b"ada-wheel")
    hashes = {}
    for name in ("external-runtime.txt", "host-runtime.txt", "starter-build.txt"):
        path = requirements / name
        path.write_text("locked==1.0.0\n", encoding="utf-8")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    starter = {
        "artifact_kind": "web-application-starter",
        "profile": "ada",
        "wheelhouse_included": True,
        "delivery_strategy": "internal-wheels-external-image-build",
    }
    (root / "manifest.json").write_text(json.dumps(starter), encoding="utf-8")
    (root / "pyproject.toml").write_text('[project]\nname="application"\n')
    manifest = {
        "schema_version": 2,
        "strategy": starter["delivery_strategy"],
        "profile": "ada",
        "python": platform.python_version(),
        "requirements": hashes,
        "packages": [
            {
                "filename": wheel.name,
                "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
            }
        ],
    }
    (wheelhouse / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    runtime = requirements / "project-runtime.txt"
    runtime.write_bytes((requirements / "external-runtime.txt").read_bytes())
    lock = {
        "schema_version": 1,
        "distribution_manifest_sha256": hashlib.sha256(
            (root / "manifest.json").read_bytes()
        ).hexdigest(),
        "wheelhouse_manifest_sha256": hashlib.sha256(
            (wheelhouse / "manifest.json").read_bytes()
        ).hexdigest(),
        "external_runtime_sha256": hashes["external-runtime.txt"],
        "project_sha256": hashlib.sha256(
            (root / "pyproject.toml").read_bytes()
        ).hexdigest(),
        "project_runtime_sha256": hashlib.sha256(runtime.read_bytes()).hexdigest(),
    }
    (requirements / "project.lock.json").write_text(json.dumps(lock))
    return root, wheel


def test_image_preflight_accepts_only_verified_internal_wheels_and_requirements(
    tmp_path,
):
    root, _wheel = _candidate(tmp_path)
    assert _verifier.verify_delivery(root) == 1


def test_image_preflight_rejects_changed_internal_wheel(tmp_path):
    root, wheel = _candidate(tmp_path)
    wheel.write_bytes(b"changed")
    with pytest.raises(_verifier.DeliveryValidationError, match="wheel integrity"):
        _verifier.verify_delivery(root)


def test_image_preflight_rejects_changed_external_requirements(tmp_path):
    root, _wheel = _candidate(tmp_path)
    (root / "requirements/host-runtime.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(
        _verifier.DeliveryValidationError, match="requirements integrity"
    ):
        _verifier.verify_delivery(root)


def test_ada_image_build_receives_external_pins_and_has_no_active_healthcheck():
    dockerfile = (_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "python:3.14.2-slim-bookworm" in dockerfile
    assert "--require-hashes" in dockerfile
    assert "project-runtime.txt" in dockerfile
    assert "external-runtime.txt" not in dockerfile
    assert "--no-index --no-deps" in dockerfile
    assert "EXPOSE 8000" in dockerfile
    assert "HEALTHCHECK" not in dockerfile
    assert "gunicorn" in dockerfile
    assert "project.lock.json" in (_ROOT / ".dockerignore").read_text()
    assert "USER app" in dockerfile
    assert "cannot run in production" not in dockerfile


def test_new_productive_python_sources_match_pedagogical_mirrors():
    paths = [
        ("docker/verify_delivery.py", "commented/docker/verify_delivery.py"),
        ("src/application/runtime.py", "commented/application/runtime.py"),
        ("src/application/wsgi.py", "commented/application/wsgi.py"),
        ("src/application/production.py", "commented/application/production.py"),
        ("gunicorn.conf.py", "commented/gunicorn.conf.py"),
    ]
    for productive, commented in paths:
        assert ast.dump(
            ast.parse((_ROOT / productive).read_text()), include_attributes=False
        ) == (
            ast.dump(
                ast.parse((_ROOT / commented).read_text()), include_attributes=False
            )
        )


def test_generated_ada_starter_keeps_editable_modules_and_uses_ada_image(
    tmp_path, monkeypatch
):
    generator_path = (
        Path(__file__).resolve().parents[5]
        / "tooling/distribution/web/generate_starter.py"
    )
    spec = importlib.util.spec_from_file_location(
        "ada_generator_image_contract", generator_path
    )
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, generator)
    spec.loader.exec_module(generator)
    contract = (
        tmp_path / "repo/scopes/ada/web/application/ada-generic-application/.env.detail"
    )
    contract.parent.mkdir(parents=True)
    contract.write_text(
        "# @distribution manual-default\nADA_TOOL_SOURCE_PROVIDER=blob\n"
    )
    monkeypatch.setitem(generator._PRODUCTS["ada"], "starter_overlay", str(_ROOT))
    monkeypatch.setattr(generator, "REPOSITORY_ROOT", tmp_path / "repo")
    generated = generator.generate_starter(
        profile="ada", destination=tmp_path / "generated"
    )
    inventory = json.loads((generated / "manifest.json").read_text())["files"]
    for relative in (
        "Dockerfile",
        ".dockerignore",
        "gunicorn.conf.py",
        "src/application/wsgi.py",
        "src/application/runtime.py",
        "src/application/modules/__init__.py",
        "configuration/templates/dev.mapping-env.csv",
    ):
        payload = (generated / relative).read_bytes()
        assert inventory[relative] == hashlib.sha256(payload).hexdigest()
    assert (generated / "Dockerfile").read_bytes() == (
        _ROOT / "Dockerfile"
    ).read_bytes()


def test_generated_ada_tooling_is_executable_and_stays_out_of_docker_context(
    tmp_path,
    monkeypatch,
):
    import os

    generator_path = (
        Path(__file__).resolve().parents[5]
        / "tooling/distribution/web/generate_starter.py"
    )
    spec = importlib.util.spec_from_file_location(
        "ada_tool_generator_contract", generator_path
    )
    assert spec is not None and spec.loader is not None
    generator = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, generator)
    spec.loader.exec_module(generator)
    env = (
        tmp_path / "repo/scopes/ada/web/application/ada-generic-application/.env.detail"
    )
    env.parent.mkdir(parents=True)
    env.write_text("# @distribution manual-default\nADA_TOOL_SOURCE_PROVIDER=blob\n")
    monkeypatch.setitem(generator._PRODUCTS["ada"], "starter_overlay", str(_ROOT))
    monkeypatch.setattr(generator, "REPOSITORY_ROOT", tmp_path / "repo")
    app = generator.generate_starter(profile="ada", destination=tmp_path / "app")
    script = app / "tooling/project.sh"
    assert script.is_file()
    if os.name != "nt":
        assert os.access(script, os.X_OK)
    assert (app / "tooling/project.cmd").is_file()
    assert (app / "tooling/project.py").is_file()
    manifests = json.loads((app / "manifest.json").read_text())["files"]
    assert (
        manifests["tooling/project.sh"]
        == hashlib.sha256(script.read_bytes()).hexdigest()
    )
    rules = (app / ".dockerignore").read_text()
    assert rules.splitlines()[0] == "*"
    assert "!tooling/" not in rules


def test_local_full_compose_uses_current_ada_durable_environment_contract():
    compose = (_ROOT / "deployment/compose/full.yaml").read_text(encoding="utf-8")

    assert (
        "ADA_STORAGE_CONTAINER_NAME: ${ADA_LOCAL_BLOB_CONTAINER:-dataproduct}"
        in compose
    )
    assert "ADA_STORAGE_CONNECTION_STRING:" in compose
    assert "ADA_COSMOS_ENDPOINT:" in compose
    assert "ADA_COSMOS_KEY:" in compose
    assert "ADA_COSMOS_DATABASE_NAME:" in compose

    for legacy in (
        "ADA_TOOL_SOURCE_BLOB_CONTAINER_NAME",
        "ADA_TOOL_SOURCE_BLOB_CONNECTION_STRING",
        "ADA_TOOL_PROJECTION_COSMOS_ENDPOINT",
        "ADA_TOOL_PROJECTION_COSMOS_KEY",
        "ADA_TOOL_PROJECTION_COSMOS_DATABASE_NAME",
    ):
        assert legacy not in compose
