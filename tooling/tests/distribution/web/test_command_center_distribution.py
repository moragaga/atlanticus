from __future__ import annotations

import importlib.util
import json
import sys
import tomllib
from pathlib import Path

import pytest

_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_WEB_ROOT = _REPOSITORY_ROOT / "tooling/distribution/web"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_command_center_starter_is_minimal_and_pinned_to_current_product(
    tmp_path,
) -> None:
    generator = _load(
        "command_center_generate_starter",
        _WEB_ROOT / "generate_starter.py",
    )
    destination = generator.generate_starter(
        profile="command-center",
        destination=tmp_path / "command-center",
    )

    starter = tomllib.loads(
        (destination / "pyproject.toml").read_text(encoding="utf-8")
    )
    product = tomllib.loads(
        (
            _REPOSITORY_ROOT / "scopes/ada-command-center/web/application/"
            "ada-command-center-generic-application/pyproject.toml"
        ).read_text(encoding="utf-8")
    )
    expected = (
        f"ada-command-center-generic-application=={product['project']['version']}"
    )

    assert starter["project"]["name"] == "ada-command-center-application-starter"
    assert expected in starter["project"]["dependencies"]
    assert (destination / "src/application/__main__.py").is_file()
    assert not (destination / "src/application/composition.py").exists()
    assert not (destination / "src/application/runtime.py").exists()
    assert not (destination / "src/application/modules").exists()
    assert not (destination / "src/application/pages").exists()
    assert not (destination / "Dockerfile").exists()
    assert not (destination / ".dockerignore").exists()
    assert not (destination / "docker").exists()

    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["profile"] == "command-center"
    assert set(manifest["configuration_templates"]) == {
        "configuration/templates/dev.mapping-env.csv",
        "configuration/templates/uat.mapping-env.csv",
        "configuration/templates/prd.mapping-env.csv",
        "configuration/templates/secrets.json",
    }
    prd = (destination / "configuration/templates/prd.mapping-env.csv").read_text(
        encoding="utf-8"
    )
    assert "ATLANTICUS_ENVIRONMENT,,production" in prd
    assert "ADA_MANAGER_PERSISTENCE_PROVIDER,,durable" in prd
    assert "ADA_COMMAND_CENTER_STORAGE_CONTAINER_NAME,,dataproduct" in prd
    secrets = json.loads(
        (destination / "configuration/templates/secrets.json").read_text(encoding="utf-8")
    )
    assert secrets == [
        {
            "var_name": "ADA_COMMAND_CENTER_STORAGE_CONNECTION_STRING",
            "secret_name": "secret-ada-command-center-storage-connection-string",
            "required_in_key_vault": True,
        },
        {
            "var_name": "ADA_COMMAND_CENTER_COSMOS_ENDPOINT",
            "secret_name": "secret-ada-command-center-cosmos-endpoint",
            "required_in_key_vault": True,
        },
        {
            "var_name": "ADA_COMMAND_CENTER_COSMOS_DATABASE_NAME",
            "secret_name": "secret-ada-command-center-cosmos-database-name",
            "required_in_key_vault": True,
        },
        {
            "var_name": "ADA_COMMAND_CENTER_COSMOS_KEY",
            "secret_name": "secret-ada-command-center-cosmos-primary-key",
            "required_in_key_vault": True,
        },
    ]

    env_detail = (destination / ".env.detail").read_text(encoding="utf-8")
    assert "\nATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID=" not in "\n" + env_detail


def test_command_center_distribution_uses_shared_wheelhouse_and_artifact_precheck(
    tmp_path, monkeypatch
) -> None:
    distributor = _load(
        "command_center_distribute",
        _WEB_ROOT / "distribute.py",
    )
    calls: list[str] = []
    destination = tmp_path / "command-center"

    def generate(*, profile, destination):
        assert profile == "command-center"
        calls.append("starter")
        destination.mkdir()
        return destination

    def build(*, profile, application, uv):
        assert profile == "command-center"
        calls.append("distribution")
        return {"status": "BUILT_UNQUALIFIED", "profile": profile}

    def qualify(**kwargs):
        assert kwargs["profile"] == "command-center"
        assert kwargs["portable"] is True
        assert kwargs["inspect_only"] is False
        calls.append("qualification")
        return {
            "status": "PASS",
            "profile": "command-center",
            "qualification": "PORTABLE",
            "checks": ["starter.entrypoint"],
            "dependency_check": "PASS",
        }

    monkeypatch.setattr(distributor, "generate_starter", generate)
    monkeypatch.setattr(distributor, "build_wheelhouse", build)
    monkeypatch.setattr(distributor, "qualify", qualify)

    result = distributor.build_web_distribution(
        profile="command-center",
        destination=destination,
        uv="uv",
        python=Path(sys.executable),
        timeout=90,
    )

    assert calls == ["starter", "distribution", "qualification"]
    assert result["status"] == "PRECHECK_PASS"
    qualification = result["stages"]["qualification"]
    assert qualification["status"] == "PRECHECK_PASS"
    assert qualification["runtime"] == "UNVERIFIED"
    assert qualification["dependency_check"] == "PASS"


def test_command_center_artifact_probe_checks_metadata_entrypoint_and_portability(
    monkeypatch,
) -> None:
    probe = _load(
        "command_center_probe",
        _WEB_ROOT / "probe_starter.py",
    )
    versions: list[str] = []

    class EntryPoint:
        name = "ada-command-center-application-starter"

        @staticmethod
        def load():
            return lambda: None

    monkeypatch.setattr(
        probe.metadata,
        "version",
        lambda package: versions.append(package) or "0.1.0",
    )
    monkeypatch.setattr(
        probe.metadata,
        "entry_points",
        lambda **kwargs: (EntryPoint(),),
    )
    monkeypatch.setattr(probe, "_verify_dependencies", lambda portable: [])

    result = probe.probe(
        profile="command-center",
        application=Path("."),
        portable=True,
    )

    assert result["status"] == "PASS"
    assert versions == [
        "ada-command-center-application-starter",
        "ada-command-center-generic-application",
    ]
    assert result["checks"] == [
        "starter.metadata",
        "root.metadata",
        "starter.entrypoint",
        "dependencies.portable",
    ]






def test_command_center_dependency_pins_match_alarm_configuration() -> None:
    configuration = tomllib.loads(
        (
            _REPOSITORY_ROOT
            / "scopes/ada-command-center/web/alarms/configuration/pyproject.toml"
        ).read_text(encoding="utf-8")
    )
    expected = (
        "ada-command-center-web-alarm-configuration=="
        f"{configuration['project']['version']}"
    )
    consumers = (
        "scopes/ada-command-center/web/alarms/persistence/pyproject.toml",
        "scopes/ada-command-center/web/alarms/projection-local/pyproject.toml",
        "scopes/ada-command-center/web/alarms/projection-cosmos/pyproject.toml",
    )
    for relative in consumers:
        metadata = tomllib.loads(
            (_REPOSITORY_ROOT / relative).read_text(encoding="utf-8")
        )
        assert expected in metadata["project"]["dependencies"]
