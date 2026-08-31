# Espejo comentado de atlanticus.web.hosting.
# Mantiene exactamente la misma semántica que producción y documenta el contrato de hosting.

from __future__ import annotations

import atexit
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Protocol

_MEMORY_GIB = 1024 * 1024 * 1024
_CGROUP_UNLIMITED_THRESHOLD = 1 << 60


# Contrato mínimo que debe exponer un runtime construido dentro de cada worker.
class WorkerRuntime(Protocol):
    @property
    def server(self) -> Callable[..., Any]: ...

    def close(self) -> None: ...


RuntimeFactory = Callable[[], WorkerRuntime]


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


# Wrapper WSGI liviano en el master; materializa el runtime únicamente durante warmup post-fork.
class WorkerApplication:
    def __init__(self, factory: RuntimeFactory) -> None:
        if not callable(factory):
            raise TypeError('factory must be callable')
        self._factory = factory
        self._lock = Lock()
        self._runtime: WorkerRuntime | None = None
        self._exit_registered = False

    @property
    def warmed_up(self) -> bool:
        return self._runtime is not None

    def warmup(self) -> None:
        if self._runtime is not None:
            return
        with self._lock:
            if self._runtime is not None:
                return
            runtime = self._factory()
            if not callable(getattr(runtime, 'server', None)):
                raise TypeError('worker runtime server must be callable')
            if not callable(getattr(runtime, 'close', None)):
                raise TypeError('worker runtime close must be callable')
            self._runtime = runtime
            if not self._exit_registered:
                atexit.register(self.close)
                self._exit_registered = True

    def __call__(self, environ: dict[str, Any], start_response: Callable[..., Any]):
        runtime = self._runtime
        if runtime is None:
            raise RuntimeError('Atlanticus Web worker runtime is not initialized')
        return runtime.server(environ, start_response)

    def close(self) -> None:
        with self._lock:
            runtime = self._runtime
            self._runtime = None
        if runtime is not None:
            runtime.close()


# Hook reusable para post_worker_init de Gunicorn.
def warmup_gunicorn_worker(worker: object) -> None:
    warmup = getattr(getattr(worker, 'wsgi', None), 'warmup', None)
    if not callable(warmup):
        raise RuntimeError('Gunicorn WSGI application does not support worker warmup')
    warmup()


# Hook reusable para worker_exit; el cierre es opcional e idempotente en la aplicación.
def close_gunicorn_worker(worker: object) -> None:
    close = getattr(getattr(worker, 'wsgi', None), 'close', None)
    if callable(close):
        close()


# La capacidad se deriva exclusivamente de recursos efectivos del runtime.
def resolve_gunicorn_capacity() -> GunicornCapacity:
    effective_cpu, cpu_source = _detect_cpu()
    memory_bytes, memory_source = _detect_memory_bytes()

    detected_workers = min(
        _resolve_workers_from_memory(memory_bytes),
        max(1, int(effective_cpu)),
    )
    detected_resources = cpu_source != 'fallback' or memory_source != 'fallback'
    detected_threads = 2 if detected_resources else 1

    workers = detected_workers
    threads = detected_threads

    return GunicornCapacity(
        workers=workers,
        threads=threads,
        effective_cpu=effective_cpu,
        cpu_source=cpu_source,
        memory_bytes=memory_bytes,
        memory_source=memory_source,
    )


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
