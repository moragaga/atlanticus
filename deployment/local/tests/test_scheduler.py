from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scheduler/scheduler.py"
SPEC = importlib.util.spec_from_file_location(
    "atlanticus_local_scheduler_test",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
scheduler = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = scheduler
SPEC.loader.exec_module(scheduler)


def _schedule(tmp_path: Path) -> object:
    env_file = tmp_path / ".env"
    config_file = tmp_path / "config.json"
    env_file.write_text("ENVIRONMENT=local\n", encoding="utf-8")
    config_file.write_text("{}\n", encoding="utf-8")
    return scheduler.ProcessSchedule(
        name="kpis",
        image="atlanticus-sample-kpis:local",
        env_file=env_file,
        config_file=config_file,
        cpus=0.5,
        memory="1g",
        replica_timeout=605,
        replica_retry_limit=0,
        cron_expression="*/10 * * * *",
        parallelism=1,
    )


def test_job_container_command_runs_full_replica(tmp_path: Path) -> None:
    schedule = _schedule(tmp_path)

    command = scheduler._docker_run_command(
        simulation="sample",
        schedule=schedule,
        execution="abcdef123456",
        replica=1,
        attempt=0,
        runtime_mount="type=volume,source=runtime,target=/app/volumen",
        network="sample_default",
    )

    assert command[0:2] == ["run", "-d"]
    assert "--run-once" not in command
    assert command[-1] == "atlanticus-sample-kpis:local"
    assert "atlanticus.simulation=sample" in command
    assert "atlanticus.role=execution" in command


def test_crontab_preserves_schedule_and_uses_utc_environment(
    tmp_path: Path,
    monkeypatch,
) -> None:
    cron_path = tmp_path / "atlanticus"
    monkeypatch.setattr(scheduler, "CRON_PATH", cron_path)
    monkeypatch.setenv("ATLANTICUS_SIMULATION", "sample")
    monkeypatch.setenv(
        "ATLANTICUS_SIMULATION_SPEC",
        "/workspace/deployment/local/simulation.json",
    )

    scheduler._write_crontab((_schedule(tmp_path),))

    rendered = cron_path.read_text(encoding="utf-8")
    assert "*/10 * * * * root python" in rendered
    assert "trigger kpis" in rendered
    assert "DOCKER_HOST=unix:///var/run/docker.sock" in rendered


def test_schedule_contract_uses_replica_timeout_as_external_limit(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"
    process = workspace / "processes/kpis"
    process.mkdir(parents=True)
    (process / ".env").write_text("ENVIRONMENT=local\n", encoding="utf-8")
    (process / "config.json").write_text(
        json.dumps(
            {
                "configuration": {
                    "replicaTimeout": 605,
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
    spec = workspace / "deployment/local/simulation.json"
    spec.parent.mkdir(parents=True)
    spec.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "simulation": "sample",
                "processes": [
                    {
                        "name": "kpis",
                        "image": "atlanticus-sample-kpis:local",
                        "env_file": "processes/kpis/.env",
                        "config_file": "processes/kpis/config.json",
                        "cpus": 0.5,
                        "memory": "1g",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(scheduler, "WORKSPACE_ROOT", workspace)
    monkeypatch.setenv("ATLANTICUS_SIMULATION", "sample")
    monkeypatch.setenv("ATLANTICUS_SIMULATION_SPEC", str(spec))

    schedule = scheduler._load_schedules()[0]

    assert schedule.replica_timeout == 605
    assert schedule.cron_expression == "*/10 * * * *"
    assert schedule.parallelism == 1


def test_commented_scheduler_is_structurally_equivalent() -> None:
    production = ast.dump(
        ast.parse(MODULE_PATH.read_text(encoding="utf-8")),
        include_attributes=False,
    )
    commented = ast.dump(
        ast.parse(
            (MODULE_PATH.parent / "commented/scheduler.py").read_text(encoding="utf-8")
        ),
        include_attributes=False,
    )

    assert production == commented
