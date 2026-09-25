from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "simulation.py"
SPEC = importlib.util.spec_from_file_location(
    "atlanticus_local_simulation_test",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
simulation = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = simulation
SPEC.loader.exec_module(simulation)


def _scheduler_source(root: Path) -> Path:
    source = root / "scheduler-source"
    source.mkdir()
    (source / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (source / "scheduler.py").write_text("VALUE = 1\n", encoding="utf-8")
    return source


def _process(root: Path) -> Path:
    process = root / "processes/kpis"
    process.mkdir(parents=True)
    (process / "pyproject.toml").write_text(
        "[project]\n"
        'name = "ada-kpi-runtime-process"\n'
        'version = "1.0.0"\n'
        'requires-python = "==3.14.2"\n'
        "dependencies = []\n\n"
        "[project.scripts]\n"
        'ada-kpi-runtime = "sample:main"\n\n'
        "[tool.atlanticus.container]\n"
        'command = "ada-kpi-runtime"\n'
        'system-profile = "base"\n\n'
        "[tool.atlanticus.container.resources]\n"
        "cpus = 0.5\n"
        'memory = "1g"\n',
        encoding="utf-8",
    )
    (process / ".env").write_text("ENVIRONMENT=local\n", encoding="utf-8")
    (process / "config.json").write_text(
        json.dumps(
            {
                "configuration": {
                    "replicaTimeout": 610,
                    "replicaRetryLimit": 0,
                    "triggerType": "Schedule",
                    "scheduleTriggerConfig": {
                        "cronExpression": "*/10 * * * *",
                        "parallelism": 1,
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    return process


def test_docker_socket_resolution_is_engine_oriented() -> None:
    assert (
        simulation.resolve_docker_socket_source(
            endpoint="unix:///var/run/docker.sock",
            operating_system="Ubuntu 24.04",
            engine_type="linux",
        )
        == "/var/run/docker.sock"
    )
    assert (
        simulation.resolve_docker_socket_source(
            endpoint="npipe:////./pipe/docker_engine",
            operating_system="Docker Desktop",
            engine_type="linux",
        )
        == "/var/run/docker.sock.raw"
    )
    with pytest.raises(simulation.LocalSimulationError, match="Linux Docker engine"):
        simulation.resolve_docker_socket_source(
            endpoint="npipe:////./pipe/docker_engine",
            operating_system="Docker Desktop",
            engine_type="windows",
        )


def test_prepare_simulation_keeps_jobs_out_of_compose(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    local = workspace / "deployment/local"
    process_root = _process(workspace)
    process = simulation.load_simulation_process(
        process_root=process_root,
        name="kpis",
        image="atlanticus-sample-kpis:local",
    )

    compose_path = simulation.prepare_simulation(
        workspace_root=workspace,
        local_root=local,
        scheduler_source=_scheduler_source(tmp_path),
        project_name="atlanticus-sample-local",
        simulation_name="sample",
        processes=(process,),
        volume_mode="bind",
        bind_runtime=workspace / ".runtime/volumen",
    )

    spec = json.loads((local / "simulation.json").read_text(encoding="utf-8"))
    assert spec["processes"][0]["config_file"] == "processes/kpis/config.json"
    assert spec["processes"][0]["env_file"] == "processes/kpis/.env"

    compose = compose_path.read_text(encoding="utf-8")
    assert "scheduler:" in compose
    assert "kpis:" not in compose
    assert "--run-once" not in compose
    assert "/var/run/docker.sock" in compose
    assert "/app/volumen" in compose


def test_commented_simulation_is_structurally_equivalent() -> None:
    production = ast.dump(
        ast.parse(MODULE_PATH.read_text(encoding="utf-8")),
        include_attributes=False,
    )
    commented = ast.dump(
        ast.parse(
            (MODULE_PATH.parent / "commented/simulation.py").read_text(encoding="utf-8")
        ),
        include_attributes=False,
    )

    assert production == commented
