from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

SCHEMA_VERSION = 1
DEFAULT_VCPU = 0.5
DEFAULT_MEMORY_GIB = 1.0
MIN_VCPU = 0.25
MAX_VCPU = 4.0
VCPU_STEP = 0.25
PROCESS_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


# Error de contrato del archivo consumer-owned que define recursos efectivos de despliegue.
class DeploymentResourcesError(ValueError):
    pass


# Par CPU/RAM ya validado contra el perfil admitido por Atlanticus.
@dataclass(frozen=True, slots=True)
class ProcessResources:
    vcpu: float
    memory_gib: float


# Normaliza y restringe CPU/RAM a la tabla acordada: pasos de 0.25 vCPU y RAM = 2 × vCPU.
def _resource(vcpu: object, memory_gib: object, *, process: str) -> ProcessResources:
    if (
        isinstance(vcpu, bool)
        or not isinstance(vcpu, (int, float))
        or isinstance(memory_gib, bool)
        or not isinstance(memory_gib, (int, float))
    ):
        raise DeploymentResourcesError(f"Deployment resources must be numeric for {process}")
    normalized_vcpu = float(vcpu)
    normalized_memory = float(memory_gib)
    if not MIN_VCPU <= normalized_vcpu <= MAX_VCPU:
        raise DeploymentResourcesError(f"Deployment vCPU is out of range for {process}")
    steps = normalized_vcpu / VCPU_STEP
    if abs(steps - round(steps)) > 1e-9:
        raise DeploymentResourcesError(f"Deployment vCPU must use 0.25 increments for {process}")
    expected_memory = normalized_vcpu * 2.0
    if abs(normalized_memory - expected_memory) > 1e-9:
        raise DeploymentResourcesError(
            "Deployment memory must be "
            f"{expected_memory:g} GiB for {normalized_vcpu:g} vCPU: {process}"
        )
    return ProcessResources(vcpu=normalized_vcpu, memory_gib=normalized_memory)


# Default global usado únicamente al crear un proceso nuevo dentro de una distribución.
def default_resources() -> ProcessResources:
    return ProcessResources(vcpu=DEFAULT_VCPU, memory_gib=DEFAULT_MEMORY_GIB)


# Lee el documento sin exigir todavía que coincida con un conjunto concreto de procesos.
def read_resources(path: Path) -> dict[str, ProcessResources]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DeploymentResourcesError(f"Deployment resources file is invalid: {path}") from error
    if not isinstance(payload, dict) or set(payload) != {"schema_version", "processes"}:
        raise DeploymentResourcesError(f"Deployment resources contract is invalid: {path}")
    if payload.get("schema_version") != SCHEMA_VERSION or not isinstance(
        payload.get("processes"), dict
    ):
        raise DeploymentResourcesError(f"Deployment resources contract is invalid: {path}")
    resources: dict[str, ProcessResources] = {}
    for process, value in payload["processes"].items():
        if not isinstance(process, str) or PROCESS_NAME_PATTERN.fullmatch(process) is None:
            raise DeploymentResourcesError(
                f"Deployment resource process name is invalid: {process}"
            )
        if not isinstance(value, dict) or set(value) != {"vcpu", "memory_gib"}:
            raise DeploymentResourcesError(f"Deployment resource entry is invalid for {process}")
        resources[process] = _resource(value["vcpu"], value["memory_gib"], process=process)
    return resources


# Exige correspondencia exacta con los procesos instalados para impedir sizing huérfano o faltante.
def require_resources(
    path: Path, expected_processes: tuple[str, ...]
) -> dict[str, ProcessResources]:
    resources = read_resources(path)
    expected = set(expected_processes)
    actual = set(resources)
    if actual != expected:
        missing = ", ".join(sorted(expected - actual)) or "none"
        unexpected = ", ".join(sorted(actual - expected)) or "none"
        raise DeploymentResourcesError(
            "Deployment resources do not match distribution processes; "
            f"missing: {missing}; unexpected: {unexpected}"
        )
    return {process: resources[process] for process in expected_processes}


# Persiste únicamente el contrato editable del consumidor; no materializa Compose.
def write_resources(path: Path, resources: Mapping[str, ProcessResources]) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "processes": {
            process: {
                "vcpu": resource.vcpu,
                "memory_gib": resource.memory_gib,
            }
            for process, resource in resources.items()
        },
    }
    try:
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError as error:
        raise DeploymentResourcesError(f"Could not write deployment resources: {path}") from error


# Docker recibe MiB enteros: GiB × 1024. Esto evita representar 1.5 GiB como un valor ambiguo.
def docker_memory(resource: ProcessResources) -> str:
    return f"{int(round(resource.memory_gib * 1024))}m"


# Renderiza sólo el override efímero de recursos que se superpone al Compose base.
def render_compose_override(resources: Mapping[str, ProcessResources]) -> str:
    services = []
    for process, resource in resources.items():
        services.extend(
            (
                f"  {process}:",
                f"    cpus: {resource.vcpu:g}",
                f"    mem_limit: {docker_memory(resource)}",
            )
        )
    return "services:\n" + "\n".join(services) + "\n"
