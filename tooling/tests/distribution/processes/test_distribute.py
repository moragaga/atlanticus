from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[3] / "distribution/processes/distribute.py"
)
SPEC = importlib.util.spec_from_file_location(
    "atlanticus_distribution_processes_test", MODULE_PATH
)
assert SPEC is not None and SPEC.loader is not None
distribution = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = distribution
SPEC.loader.exec_module(distribution)


def _write_process(root: Path, name: str, project: str | None = None) -> None:
    process = root / "artifacts/processes" / name
    (process / "wheels").mkdir(parents=True)
    (process / "src").mkdir()
    project_name = project or f"{name}-package"
    (process / "pyproject.toml").write_text(
        "[project]\n"
        f'name = "{project_name}"\n'
        'version = "1.0.0"\n'
        f'description = "Process {name}."\n'
        'requires-python = "==3.14.2"\n'
        "dependencies = []\n\n"
        "[project.scripts]\n"
        f'{name} = "sample:main"\n\n'
        "[tool.atlanticus.container]\n"
        f'command = "{name}"\n'
        'system-profile = "base"\n',
        encoding="utf-8",
    )
    (process / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    (process / ".env.detail").write_text("ENVIRONMENT=local\n", encoding="utf-8")
    (process / "config.detail.json").write_text("{}\n", encoding="utf-8")
    (process / "secrets.detail.json").write_text("[]\n", encoding="utf-8")


def _write_source(root: Path, relative: str, name: str) -> None:
    process = root / relative
    process.mkdir(parents=True)
    (process / "pyproject.toml").write_text(
        "[project]\n"
        f'name = "{name}-package"\n'
        'version = "1.0.0"\n'
        f'description = "Process {name}."\n'
        'requires-python = "==3.14.2"\n'
        "dependencies = []\n\n"
        "[project.scripts]\n"
        f'{name} = "sample:main"\n\n'
        "[tool.atlanticus.container]\n"
        f'command = "{name}"\n'
        'system-profile = "base"\n',
        encoding="utf-8",
    )


def _write_transport(root: Path) -> None:
    deployment = root / "deployment/processes"
    deployment.mkdir(parents=True)
    (deployment / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (deployment / ".dockerignore").write_text("*\n", encoding="utf-8")


def _patch_generation_context(monkeypatch, tmp_path: Path) -> None:
    template = tmp_path / "consumer"
    template.mkdir()
    for name in ("process.py", "process.sh", "process.cmd"):
        (template / name).write_text(name, encoding="utf-8")
    monkeypatch.setattr(distribution, "_consumer_template_root", lambda: template)
    monkeypatch.setattr(distribution, "_generated_at", lambda: "2026-09-22T23:30:00Z")
    monkeypatch.setattr(
        distribution,
        "_source_revision",
        lambda repository_root: "b93bfdc1b691daff72796c86d91e2890d94a8079",
    )


def test_deployment_catalog_is_stable() -> None:
    assert [
        (item.number, item.process, item.excecution_file)
        for item in distribution.DEPLOYMENT_CATALOG
    ] == [
        ("01", "operational-data-pi", "pi-web-api"),
        ("02", "operational-data-notpii", "notpii"),
        ("03", "operational-data-dispatch", "dispatch"),
        ("04", "operational-data-blockgrade", "blockgrade"),
        ("05", "operational-data-fabrica", "fabrica"),
        ("06", "operational-data-remanentes", "remanentes"),
        ("21", "ada-kpi-runtime", "kpis"),
        ("22", "ada-kpi-historian", "kpis-historian"),
        ("41", "ada-kpi-delivery", "kpis-delivery"),
        ("42", "ada-kpi-timeseries-delivery", "kpis-timeseries-delivery"),
    ]


def test_mixed_explicit_processes_generate_pipeline_contract(
    tmp_path: Path, monkeypatch
) -> None:
    _write_transport(tmp_path)
    for name in (
        "operational-data-pi",
        "operational-data-dispatch",
        "ada-kpi-runtime",
        "ada-kpi-delivery",
    ):
        _write_process(tmp_path, name)
    _patch_generation_context(monkeypatch, tmp_path)

    target = distribution.distribute(
        repository_root=tmp_path,
        output_root=tmp_path / "distribution",
        distribution_name="ada-generic",
        selections=(
            "ada-kpi-delivery",
            "operational-data-dispatch",
            "ada-kpi-runtime",
            "operational-data-pi",
        ),
        targets=(),
    )

    manifest = json.loads((target / "distribution.json").read_text(encoding="utf-8"))
    assert manifest["generated_at"] == "2026-09-22T23:30:00Z"
    assert manifest["source"] == {
        "repository": "atlanticus",
        "revision": "b93bfdc1b691daff72796c86d91e2890d94a8079",
    }
    assert [item["process"] for item in manifest["processes"]] == [
        "operational-data-pi",
        "operational-data-dispatch",
        "ada-kpi-runtime",
        "ada-kpi-delivery",
    ]
    assert manifest["processes"][2]["description"] == "Process ada-kpi-runtime."
    assert manifest["processes"][2]["runtime"] == {
        "language": "python",
        "version": "3.14.2",
    }
    assert manifest["processes"][2]["deployment"] == {
        "excecution_file": "kpis",
        "container_name": "job21",
    }

    services = json.loads((target / "services.json").read_text(encoding="utf-8"))
    assert services == [
        {
            "repository": "pi-web-api",
            "excecution_file": "pi-web-api",
            "container_name": "job01",
            "config_file": "processes/pi-web-api/config.json",
            "to_deploy": True,
            "to_stop": False,
            "to_working_hours_dev": True,
            "to_working_hours_uat": True,
        },
        {
            "repository": "dispatch",
            "excecution_file": "dispatch",
            "container_name": "job03",
            "config_file": "processes/dispatch/config.json",
            "to_deploy": True,
            "to_stop": False,
            "to_working_hours_dev": True,
            "to_working_hours_uat": True,
        },
        {
            "repository": "kpis",
            "excecution_file": "kpis",
            "container_name": "job21",
            "config_file": "processes/kpis/config.json",
            "to_deploy": True,
            "to_stop": False,
            "to_working_hours_dev": True,
            "to_working_hours_uat": True,
        },
        {
            "repository": "kpis-delivery",
            "excecution_file": "kpis-delivery",
            "container_name": "job41",
            "config_file": "processes/kpis-delivery/config.json",
            "to_deploy": True,
            "to_stop": False,
            "to_working_hours_dev": True,
            "to_working_hours_uat": True,
        },
    ]
    assert {path.name for path in (target / "processes").iterdir()} == {
        "pi-web-api",
        "dispatch",
        "kpis",
        "kpis-delivery",
    }
    compose = (target / "compose.yaml").read_text(encoding="utf-8")
    assert "FILENAME: kpis" in compose
    assert "FILENAME: operational-data-pi" not in compose
    assert not (target / ".runtime").exists()


def test_regeneration_preserves_retained_consumer_configuration(
    tmp_path: Path, monkeypatch
) -> None:
    _write_transport(tmp_path)
    for name in ("operational-data-pi", "ada-kpi-runtime"):
        _write_process(tmp_path, name)
    _patch_generation_context(monkeypatch, tmp_path)

    target = distribution.distribute(
        repository_root=tmp_path,
        output_root=tmp_path / "distribution",
        distribution_name="consumer",
        selections=("operational-data-pi", "ada-kpi-runtime"),
        targets=(),
    )
    retained = target / "processes/kpis"
    for name in distribution.CONSUMER_CONFIGURATION_FILES:
        (retained / name).write_text(f"{name}\n", encoding="utf-8")

    target = distribution.distribute(
        repository_root=tmp_path,
        output_root=tmp_path / "distribution",
        distribution_name="consumer",
        selections=("ada-kpi-runtime",),
        targets=(),
    )

    for name in distribution.CONSUMER_CONFIGURATION_FILES:
        assert (target / "processes/kpis" / name).read_text() == f"{name}\n"
    assert not (target / "processes/pi-web-api").exists()


def test_target_expansion_uses_current_source_layouts(
    tmp_path: Path, monkeypatch
) -> None:
    _write_transport(tmp_path)
    _write_process(tmp_path, "ada-kpi-runtime")
    _write_process(tmp_path, "operational-data-pi")
    _write_source(
        tmp_path,
        "scopes/ada/backend/processes/kpi-runtime",
        "ada-kpi-runtime",
    )
    _write_source(
        tmp_path,
        "scopes/operational-data/processes/pi",
        "operational-data-pi",
    )
    _patch_generation_context(monkeypatch, tmp_path)

    target = distribution.distribute(
        repository_root=tmp_path,
        output_root=tmp_path / "distribution",
        distribution_name="mixed-targets",
        selections=(),
        targets=("ada-backend", "operational-data"),
    )

    manifest = json.loads((target / "distribution.json").read_text(encoding="utf-8"))
    assert [item["process"] for item in manifest["processes"]] == [
        "operational-data-pi",
        "ada-kpi-runtime",
    ]
    assert {path.name for path in (target / "processes").iterdir()} == {
        "pi-web-api",
        "kpis",
    }
