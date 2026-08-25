from __future__ import annotations

# Calcula una capacidad conservadora de Gunicorn usando límites reales de cgroup cuando están disponibles.

import os
from dataclasses import dataclass
from pathlib import Path

from atlanticus.web.errors import WebConfigurationError

_MEMORY_GIB = 1024 * 1024 * 1024
_CGROUP_UNLIMITED_THRESHOLD = 1 << 60


@dataclass(frozen=True, slots=True)
class GunicornCapacity:
    workers: int
    threads: int
    effective_cpu: float
    cpu_source: str
    memory_bytes: int | None
    memory_source: str

    @property
    def memory_gib(self) -> float | None:
        if self.memory_bytes is None:
            return None
        return round(self.memory_bytes / _MEMORY_GIB, 2)


def resolve_gunicorn_capacity(values: dict[str, str] | None = None) -> GunicornCapacity:
    source = os.environ if values is None else values
    # Priorizamos límites del contenedor; os.cpu_count puede reflejar el host y sobredimensionar workers.
    effective_cpu, cpu_source = _detect_cpu()
    memory_bytes, memory_source = _detect_memory_bytes()

    # La memoria limita primero la cantidad de procesos; luego la CPU impone el techo final.
    detected_workers = min(
        _resolve_workers_from_memory(memory_bytes),
        max(1, int(effective_cpu)),
    )
    detected_resources = cpu_source != 'fallback' or memory_source != 'fallback'
    detected_threads = 2 if detected_resources else 1

    # Los overrides permiten corregir una instancia particular sin cambiar código.
    workers = _read_positive_override(source, 'ATLANTICUS_WEB_WORKERS') or detected_workers
    threads = _read_positive_override(source, 'ATLANTICUS_WEB_THREADS') or detected_threads

    return GunicornCapacity(
        workers=workers,
        threads=threads,
        effective_cpu=effective_cpu,
        cpu_source=cpu_source,
        memory_bytes=memory_bytes,
        memory_source=memory_source,
    )


def _read_positive_override(values: dict[str, str], name: str) -> int | None:
    raw_value = values.get(name)
    if raw_value is None or not raw_value.strip():
        return None
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise WebConfigurationError(f'{name} must be a positive integer') from exc
    if value <= 0:
        raise WebConfigurationError(f'{name} must be a positive integer')
    return value


def _read_text(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding='utf-8', errors='replace').strip()
    except OSError:
        return None


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def _read_cgroup_v2_cpu() -> float | None:
    value = _read_text('/sys/fs/cgroup/cpu.max')
    if not value:
        return None
    parts = value.split()
    if not parts or parts[0] == 'max':
        return None
    quota = _to_int(parts[0])
    period = _to_int(parts[1]) if len(parts) > 1 else None
    if quota is None or period is None or period <= 0:
        return None
    return quota / period


def _read_cgroup_v1_cpu() -> float | None:
    quota = _to_int(
        _read_text('/sys/fs/cgroup/cpu/cpu.cfs_quota_us')
        or _read_text('/sys/fs/cgroup/cpu,cpuacct/cpu.cfs_quota_us')
    )
    period = _to_int(
        _read_text('/sys/fs/cgroup/cpu/cpu.cfs_period_us')
        or _read_text('/sys/fs/cgroup/cpu,cpuacct/cpu.cfs_period_us')
    )
    if quota is None or period is None or quota <= 0 or period <= 0:
        return None
    return quota / period


def _count_cpuset(value: str | None) -> int | None:
    if not value:
        return None
    total = 0
    for item in value.split(','):
        item = item.strip()
        if not item:
            continue
        if '-' in item:
            start_raw, end_raw = item.split('-', 1)
            start = _to_int(start_raw)
            end = _to_int(end_raw)
            if start is not None and end is not None:
                total += max(0, end - start + 1)
        elif _to_int(item) is not None:
            total += 1
    return total or None


def _read_cpuset_cpu() -> int | None:
    return _count_cpuset(
        _read_text('/sys/fs/cgroup/cpuset.cpus.effective')
        or _read_text('/sys/fs/cgroup/cpuset.cpus')
        or _read_text('/sys/fs/cgroup/cpuset/cpuset.cpus')
    )


def _detect_cpu() -> tuple[float, str]:
    cgroup_v2 = _read_cgroup_v2_cpu()
    if cgroup_v2 is not None:
        return max(1.0, cgroup_v2), 'cgroup_v2_cpu_max'
    cgroup_v1 = _read_cgroup_v1_cpu()
    if cgroup_v1 is not None:
        return max(1.0, cgroup_v1), 'cgroup_v1_cpu_quota'
    cpuset = _read_cpuset_cpu()
    if cpuset is not None:
        return float(max(1, cpuset)), 'cpuset'
    cpu_count = os.cpu_count()
    if cpu_count is not None:
        return float(max(1, cpu_count)), 'os_cpu_count'
    return 1.0, 'fallback'


def _read_cgroup_memory_bytes() -> int | None:
    raw_value = _read_text('/sys/fs/cgroup/memory.max') or _read_text(
        '/sys/fs/cgroup/memory/memory.limit_in_bytes'
    )
    if raw_value == 'max':
        return None
    value = _to_int(raw_value)
    if value is None or value <= 0 or value >= _CGROUP_UNLIMITED_THRESHOLD:
        return None
    return value


def _read_proc_memtotal_bytes() -> int | None:
    content = _read_text('/proc/meminfo')
    if not content:
        return None
    for line in content.splitlines():
        if not line.startswith('MemTotal:'):
            continue
        parts = line.split()
        if len(parts) < 2:
            return None
        memory_kib = _to_int(parts[1])
        return None if memory_kib is None else memory_kib * 1024
    return None


def _detect_memory_bytes() -> tuple[int | None, str]:
    cgroup_memory = _read_cgroup_memory_bytes()
    if cgroup_memory is not None:
        return cgroup_memory, 'cgroup_memory_max'
    proc_memory = _read_proc_memtotal_bytes()
    if proc_memory is not None:
        return proc_memory, 'proc_meminfo'
    return None, 'fallback'


def _resolve_workers_from_memory(memory_bytes: int | None) -> int:
    if memory_bytes is None:
        return 1
    memory_gib = memory_bytes / _MEMORY_GIB
    if memory_gib <= 2.0:
        return 1
    if memory_gib <= 6.0:
        return 2
    return 3
