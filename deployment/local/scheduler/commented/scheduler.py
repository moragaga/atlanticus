from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

WORKSPACE_ROOT = Path("/workspace")
RUNTIME_TARGET = "/app/volumen"
CRON_PATH = Path("/etc/cron.d/atlanticus")
PROCESS_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


# Error operativo del simulador local de jobs.
class SchedulerError(RuntimeError):
    pass


# Contrato resuelto desde simulation.json y el config.json activo.
@dataclass(frozen=True, slots=True)
class ProcessSchedule:
    name: str
    image: str
    env_file: Path
    config_file: Path
    cpus: float
    memory: str
    replica_timeout: int
    replica_retry_limit: int
    cron_expression: str
    parallelism: int


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SchedulerError(f"JSON file is invalid: {path}") from error


def _spec_path() -> Path:
    value = os.environ.get("ATLANTICUS_SIMULATION_SPEC")
    if not value:
        raise SchedulerError("ATLANTICUS_SIMULATION_SPEC is required")
    return Path(value)


def _simulation_name() -> str:
    value = os.environ.get("ATLANTICUS_SIMULATION")
    if not value or PROCESS_NAME_PATTERN.fullmatch(value) is None:
        raise SchedulerError("ATLANTICUS_SIMULATION is invalid")
    return value


def _workspace_path(relative: object, *, field: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise SchedulerError(f"Simulation {field} is invalid")
    path = (WORKSPACE_ROOT / relative).resolve()
    try:
        path.relative_to(WORKSPACE_ROOT)
    except ValueError as error:
        raise SchedulerError(
            f"Simulation {field} must remain inside {WORKSPACE_ROOT}: {relative}"
        ) from error
    return path


# Resuelve schedules vigentes al iniciar o disparar una ejecución.
def _load_schedules() -> tuple[ProcessSchedule, ...]:
    spec = _read_json(_spec_path())
    if (
        not isinstance(spec, dict)
        or spec.get("schema_version") != 1
        or spec.get("simulation") != _simulation_name()
        or not isinstance(spec.get("processes"), list)
    ):
        raise SchedulerError(f"Simulation contract is invalid: {_spec_path()}")
    schedules = tuple(_schedule_from_entry(item) for item in spec["processes"])
    if not schedules:
        raise SchedulerError("Simulation process set is empty")
    names = tuple(item.name for item in schedules)
    if len(names) != len(set(names)):
        raise SchedulerError("Simulation process names contain duplicates")
    return schedules


# Valida únicamente campos de orquestación; el runtime conserva su lógica interna.
def _schedule_from_entry(entry: object) -> ProcessSchedule:
    if not isinstance(entry, dict):
        raise SchedulerError("Simulation process entry is invalid")
    name = entry.get("name")
    image = entry.get("image")
    cpus = entry.get("cpus")
    memory = entry.get("memory")
    if not isinstance(name, str) or PROCESS_NAME_PATTERN.fullmatch(name) is None:
        raise SchedulerError("Simulation process name is invalid")
    if not isinstance(image, str) or not image:
        raise SchedulerError(f"Simulation image is invalid for {name}")
    if isinstance(cpus, bool) or not isinstance(cpus, (int, float)) or cpus <= 0:
        raise SchedulerError(f"Simulation cpus are invalid for {name}")
    if not isinstance(memory, str) or not memory:
        raise SchedulerError(f"Simulation memory is invalid for {name}")
    env_file = _workspace_path(entry.get("env_file"), field="env_file")
    config_file = _workspace_path(entry.get("config_file"), field="config_file")
    if not env_file.is_file():
        raise SchedulerError(f"Simulation .env file not found: {env_file}")
    if not config_file.is_file():
        raise SchedulerError(f"Simulation config file not found: {config_file}")
    config = _read_json(config_file)
    if not isinstance(config, dict):
        raise SchedulerError(f"Process config is invalid: {config_file}")
    configuration = config.get("configuration")
    if not isinstance(configuration, dict):
        raise SchedulerError(f"Process configuration is invalid: {config_file}")
    if configuration.get("triggerType") != "Schedule":
        raise SchedulerError(f"Process triggerType must be Schedule: {config_file}")
    replica_timeout = configuration.get("replicaTimeout")
    replica_retry_limit = configuration.get("replicaRetryLimit")
    schedule = configuration.get("scheduleTriggerConfig")
    if (
        isinstance(replica_timeout, bool)
        or not isinstance(replica_timeout, int)
        or replica_timeout <= 0
    ):
        raise SchedulerError(f"replicaTimeout is invalid: {config_file}")
    if (
        isinstance(replica_retry_limit, bool)
        or not isinstance(replica_retry_limit, int)
        or replica_retry_limit < 0
    ):
        raise SchedulerError(f"replicaRetryLimit is invalid: {config_file}")
    if not isinstance(schedule, dict):
        raise SchedulerError(f"scheduleTriggerConfig is invalid: {config_file}")
    cron_expression = schedule.get("cronExpression")
    parallelism = schedule.get("parallelism")
    if not isinstance(cron_expression, str) or len(cron_expression.split()) != 5:
        raise SchedulerError(f"cronExpression must contain five fields: {config_file}")
    if (
        isinstance(parallelism, bool)
        or not isinstance(parallelism, int)
        or parallelism <= 0
    ):
        raise SchedulerError(f"parallelism is invalid: {config_file}")
    return ProcessSchedule(
        name=name,
        image=image,
        env_file=env_file,
        config_file=config_file,
        cpus=float(cpus),
        memory=memory,
        replica_timeout=replica_timeout,
        replica_retry_limit=replica_retry_limit,
        cron_expression=cron_expression,
        parallelism=parallelism,
    )


def _docker(
    arguments: list[str],
    *,
    check: bool = True,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["docker", *arguments],
            check=check,
            capture_output=capture_output,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise SchedulerError(f"Docker command failed: {' '.join(arguments)}") from error


# Las labels aíslan cada simulación y permiten limpieza segura.
def _execution_container_ids(simulation: str) -> tuple[str, ...]:
    completed = _docker(
        [
            "ps",
            "-aq",
            "--filter",
            f"label=atlanticus.simulation={simulation}",
            "--filter",
            "label=atlanticus.role=execution",
        ]
    )
    return tuple(line for line in completed.stdout.splitlines() if line)


def _cleanup_executions(simulation: str) -> None:
    ids = _execution_container_ids(simulation)
    if ids:
        _docker(["rm", "-f", *ids])


# Reutiliza el mount ya resuelto por Docker para named volume o bind.
def _self_mount() -> str:
    hostname = os.environ.get("HOSTNAME")
    if not hostname:
        raise SchedulerError("Scheduler HOSTNAME is unavailable")
    completed = _docker(["inspect", "--format", "{{json .Mounts}}", hostname])
    try:
        mounts = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise SchedulerError("Scheduler Docker mounts are invalid") from error
    if not isinstance(mounts, list):
        raise SchedulerError("Scheduler Docker mounts are invalid")
    for mount in mounts:
        if not isinstance(mount, dict) or mount.get("Destination") != RUNTIME_TARGET:
            continue
        mount_type = mount.get("Type")
        if mount_type == "volume":
            source = mount.get("Name")
        elif mount_type == "bind":
            source = mount.get("Source")
        else:
            raise SchedulerError(f"Unsupported runtime mount type: {mount_type}")
        if not isinstance(source, str) or not source:
            raise SchedulerError("Scheduler runtime mount source is invalid")
        return f"type={mount_type},source={source},target={RUNTIME_TARGET}"
    raise SchedulerError(f"Scheduler runtime mount not found: {RUNTIME_TARGET}")


# Hereda la red del scheduler para que las réplicas compartan conectividad local.
def _self_network() -> str:
    hostname = os.environ.get("HOSTNAME")
    if not hostname:
        raise SchedulerError("Scheduler HOSTNAME is unavailable")
    completed = _docker(
        ["inspect", "--format", "{{json .NetworkSettings.Networks}}", hostname]
    )
    try:
        networks = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise SchedulerError("Scheduler Docker networks are invalid") from error
    if not isinstance(networks, dict) or not networks:
        raise SchedulerError("Scheduler Docker network is unavailable")
    return sorted(networks)[0]


def _container_name(
    *,
    simulation: str,
    schedule: ProcessSchedule,
    execution: str,
    replica: int,
    attempt: int,
) -> str:
    return (
        f"atlanticus-{simulation}-{schedule.name}-{execution[:8]}-r{replica}-a{attempt}"
    )


# Construye una réplica completa; nunca agrega --run-once.
def _docker_run_command(
    *,
    simulation: str,
    schedule: ProcessSchedule,
    execution: str,
    replica: int,
    attempt: int,
    runtime_mount: str,
    network: str,
) -> list[str]:
    name = _container_name(
        simulation=simulation,
        schedule=schedule,
        execution=execution,
        replica=replica,
        attempt=attempt,
    )
    return [
        "run",
        "-d",
        "--name",
        name,
        "--label",
        f"atlanticus.simulation={simulation}",
        "--label",
        "atlanticus.role=execution",
        "--label",
        f"atlanticus.process={schedule.name}",
        "--label",
        f"atlanticus.execution={execution}",
        "--label",
        f"atlanticus.replica={replica}",
        "--label",
        f"atlanticus.attempt={attempt}",
        "--env-file",
        str(schedule.env_file),
        "--mount",
        runtime_mount,
        "--network",
        network,
        "--cpus",
        f"{schedule.cpus:g}",
        "--memory",
        schedule.memory,
        schedule.image,
    ]


# replicaTimeout actúa como techo externo de vida de la réplica.
def _wait_for_container(name: str, timeout: int) -> int:
    try:
        completed = subprocess.run(
            ["docker", "wait", name],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        print(f"{name} timed out after {timeout}s", flush=True)
        _docker(["stop", "--time", "10", name], check=False)
        return 124
    except (OSError, subprocess.CalledProcessError) as error:
        raise SchedulerError(
            f"Could not wait for execution container: {name}"
        ) from error
    try:
        return int(completed.stdout.strip())
    except ValueError as error:
        raise SchedulerError(f"Execution exit code is invalid for {name}") from error


# Aplica replicaRetryLimit sin alterar el loop interno del proceso.
def _run_replica(
    *,
    simulation: str,
    schedule: ProcessSchedule,
    execution: str,
    replica: int,
    runtime_mount: str,
    network: str,
) -> int:
    attempts = schedule.replica_retry_limit + 1
    last_code = 1
    for attempt in range(attempts):
        command = _docker_run_command(
            simulation=simulation,
            schedule=schedule,
            execution=execution,
            replica=replica,
            attempt=attempt,
            runtime_mount=runtime_mount,
            network=network,
        )
        name = command[command.index("--name") + 1]
        print(
            f"{schedule.name} execution={execution} replica={replica} "
            f"attempt={attempt} START",
            flush=True,
        )
        _docker(command)
        try:
            last_code = _wait_for_container(name, schedule.replica_timeout)
        finally:
            _docker(["rm", "-f", name], check=False)
        if last_code == 0:
            print(
                f"{schedule.name} execution={execution} replica={replica} COMPLETED",
                flush=True,
            )
            return 0
        print(
            f"{schedule.name} execution={execution} replica={replica} "
            f"FAILED exit_code={last_code}",
            flush=True,
        )
    return last_code


# Cada cron crea una ejecución independiente y permite overlap entre ejecuciones.
def _trigger(process_name: str) -> int:
    schedules = {item.name: item for item in _load_schedules()}
    schedule = schedules.get(process_name)
    if schedule is None:
        raise SchedulerError(f"Scheduled process not found: {process_name}")
    simulation = _simulation_name()
    execution = uuid.uuid4().hex
    runtime_mount = _self_mount()
    network = _self_network()
    print(
        f"{schedule.name} execution={execution} TRIGGER "
        f"parallelism={schedule.parallelism}",
        flush=True,
    )
    with ThreadPoolExecutor(max_workers=schedule.parallelism) as executor:
        futures = tuple(
            executor.submit(
                _run_replica,
                simulation=simulation,
                schedule=schedule,
                execution=execution,
                replica=replica,
                runtime_mount=runtime_mount,
                network=network,
            )
            for replica in range(1, schedule.parallelism + 1)
        )
        results = tuple(future.result() for future in futures)
    return 0 if all(code == 0 for code in results) else 1


# Cron del sistema interpreta las expresiones de cinco campos en UTC.
def _write_crontab(schedules: tuple[ProcessSchedule, ...]) -> None:
    lines = [
        "SHELL=/bin/sh",
        "PATH=/usr/local/bin:/usr/bin:/bin",
        f"ATLANTICUS_SIMULATION={_simulation_name()}",
        f"ATLANTICUS_SIMULATION_SPEC={_spec_path()}",
        "DOCKER_HOST=unix:///var/run/docker.sock",
        "",
    ]
    for schedule in schedules:
        lines.append(
            f"{schedule.cron_expression} root "
            f"python /app/scheduler/scheduler.py trigger {schedule.name} "
            ">> /proc/1/fd/1 2>> /proc/1/fd/2"
        )
    CRON_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    CRON_PATH.chmod(0o644)


# El scheduler es el único contenedor residente de la simulación.
def _serve() -> int:
    _docker(["version"])
    simulation = _simulation_name()
    _cleanup_executions(simulation)
    schedules = _load_schedules()
    _write_crontab(schedules)
    for schedule in schedules:
        print(
            f"{schedule.name} cron={schedule.cron_expression} "
            f"timeout={schedule.replica_timeout}s "
            f"retries={schedule.replica_retry_limit} "
            f"parallelism={schedule.parallelism}",
            flush=True,
        )
    os.execvp("cron", ["cron", "-f"])
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Atlanticus local job scheduler.")
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("serve")
    trigger = subparsers.add_parser("trigger")
    trigger.add_argument("process")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.action == "serve":
            return _serve()
        if arguments.action == "trigger":
            return _trigger(arguments.process)
        raise SchedulerError(f"Unsupported scheduler action: {arguments.action}")
    except SchedulerError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
