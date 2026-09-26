from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[3] / "distribution/processes/consumer/process.py"
)
SPEC = importlib.util.spec_from_file_location(
    "atlanticus_consumer_process_test", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
consumer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = consumer
SPEC.loader.exec_module(consumer)


def _distribution(root: Path, *, with_env: bool) -> None:
    alias = "kpis"
    (root / f"processes/{alias}/wheels").mkdir(parents=True)
    (root / f"processes/{alias}/src").mkdir()
    (root / f"processes/{alias}/pyproject.toml").write_text("", encoding="utf-8")
    (root / f"processes/{alias}/uv.lock").write_text("", encoding="utf-8")
    if with_env:
        (root / f"processes/{alias}/.env").write_text(
            "ENVIRONMENT=local\n", encoding="utf-8"
        )
    (root / "distribution.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "sample",
                "generated_at": "2026-09-22T23:30:00Z",
                "source": {
                    "repository": "atlanticus",
                    "revision": "b93bfdc1b691daff72796c86d91e2890d94a8079",
                },
                "processes": [
                    {
                        "process": "ada-kpi-runtime",
                        "project": "ada-kpi-runtime-process",
                        "version": "1.0.0",
                        "description": "KPI runtime process composition.",
                        "runtime": {
                            "language": "python",
                            "version": "3.14.2",
                        },
                        "deployment": {
                            "execution_file": alias,
                            "container_name": "job21",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (root / "services.json").write_text(
        json.dumps(
            [
                {
                    "repository": alias,
                    "execution_file": alias,
                    "container_name": "job21",
                    "config_file": f"processes/{alias}/config.json",
                    "to_deploy": True,
                    "to_stop": False,
                    "to_working_hours_dev": True,
                    "to_working_hours_uat": True,
                }
            ]
        ),
        encoding="utf-8",
    )
    marker = (
        'x-atlanticus-distribution-contract: "1"\n'
        f"services:\n  {alias}:\n    build:\n      args:\n        FILENAME: {alias}\n"
    )
    local = root / "deployment/local"
    scheduler = local / "scheduler"
    scheduler.mkdir(parents=True)
    (local / "compose.yaml").write_text(marker, encoding="utf-8")
    (local / "compose.bind.yaml").write_text(marker, encoding="utf-8")
    (local / "simulation.py").write_text("VALUE = 1\n", encoding="utf-8")
    (scheduler / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (scheduler / "scheduler.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")


def test_validate_requires_local_environment(tmp_path: Path) -> None:
    _distribution(tmp_path, with_env=False)

    try:
        consumer._validate_distribution(tmp_path, require_environment=True)
    except consumer.ConsumerProcessError as error:
        assert "Local process .env file not found" in str(error)
    else:
        raise AssertionError("Expected missing .env to fail validation")


def test_validate_accepts_complete_distribution(tmp_path: Path) -> None:
    _distribution(tmp_path, with_env=True)

    assert consumer._validate_distribution(tmp_path, require_environment=True) == (
        "kpis",
    )


def test_validate_rejects_services_drift(tmp_path: Path) -> None:
    _distribution(tmp_path, with_env=True)
    services_path = tmp_path / "services.json"
    services = json.loads(services_path.read_text(encoding="utf-8"))
    services[0]["container_name"] = "job99"
    services_path.write_text(json.dumps(services), encoding="utf-8")

    try:
        consumer._validate_distribution(tmp_path, require_environment=True)
    except consumer.ConsumerProcessError as error:
        assert "Pipeline services manifest does not match" in str(error)
    else:
        raise AssertionError("Expected services.json drift to fail validation")


def test_validate_rejects_legacy_manifest_execution_key(tmp_path: Path) -> None:
    _distribution(tmp_path, with_env=True)
    manifest_path = tmp_path / "distribution.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    deployment = manifest["processes"][0]["deployment"]
    deployment["excecution_file"] = deployment.pop("execution_file")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    try:
        consumer._validate_distribution(tmp_path, require_environment=True)
    except consumer.ConsumerProcessError as error:
        assert "Distribution deployment metadata is invalid" in str(error)
    else:
        raise AssertionError("Legacy manifest key must be rejected")


def test_validate_rejects_legacy_services_execution_key(tmp_path: Path) -> None:
    _distribution(tmp_path, with_env=True)
    services_path = tmp_path / "services.json"
    services = json.loads(services_path.read_text(encoding="utf-8"))
    services[0]["excecution_file"] = services[0].pop("execution_file")
    services_path.write_text(json.dumps(services), encoding="utf-8")

    try:
        consumer._validate_distribution(tmp_path, require_environment=True)
    except consumer.ConsumerProcessError as error:
        assert "Pipeline services manifest does not match" in str(error)
    else:
        raise AssertionError("Legacy services key must be rejected")


def test_integrate_rejects_unsafe_archive_without_changing_distribution(
    tmp_path: Path,
) -> None:
    _distribution(tmp_path, with_env=True)
    manifest_path = tmp_path / "distribution.json"
    before = manifest_path.read_bytes()
    extension_path = tmp_path.parent / "unsafe.extension.zip"
    with zipfile.ZipFile(extension_path, "w") as archive:
        archive.writestr(
            "extension.json",
            json.dumps(
                {
                    "schema_version": 1,
                    "name": "unsafe",
                    "generated_at": "2026-09-26T00:00:00Z",
                    "source": {"repository": "atlanticus", "revision": "a" * 40},
                    "processes": [
                        {
                            "process": "operational-data-meteodata",
                            "project": "atlanticus-operational-data-meteodata-process",
                            "version": "1.0.0",
                            "description": "Meteodata",
                            "runtime": {"language": "python", "version": "3.14.2"},
                            "deployment": {
                                "execution_file": "meteodata",
                                "container_name": "job08",
                            },
                        }
                    ],
                }
            ),
        )
        archive.writestr("../unexpected.txt", "unsafe")
    try:
        consumer._integrate(tmp_path, extension_path)
    except consumer.ConsumerProcessError as error:
        assert "Unsafe extension archive entry" in str(error)
    else:
        raise AssertionError("Path traversal must be rejected")
    assert manifest_path.read_bytes() == before
    assert not (tmp_path.parent / "unexpected.txt").exists()
