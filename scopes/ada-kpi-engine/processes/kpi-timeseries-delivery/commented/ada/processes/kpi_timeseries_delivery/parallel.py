# Publicación concurrente acotada por Tool.
# Espejo pedagógico; los comentarios no alteran el AST productivo.
from __future__ import annotations

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Protocol

from ada.kpis.delivery import KpiTimeseriesSnapshot
from ada.processes.kpi_timeseries_delivery.models import KpiTimeseriesPublication


# Esta clase delimita una responsabilidad concreta del proceso.
class _SnapshotPublisher(Protocol):
# Esta función conserva los contratos e invariantes declarados por el módulo.
    def publish(self, snapshot: KpiTimeseriesSnapshot) -> KpiTimeseriesPublication: ...


# El dataclass siguiente representa un contrato de datos explícito.
@dataclass(frozen=True, slots=True)
# Esta clase delimita una responsabilidad concreta del proceso.
class KpiTimeseriesPublicationTask:
    tool_key: str
    snapshot: KpiTimeseriesSnapshot

# Esta función conserva los contratos e invariantes declarados por el módulo.
    def __post_init__(self) -> None:
        if not isinstance(self.tool_key, str) or not self.tool_key:
            raise ValueError('tool_key must be non-empty text')
        if self.tool_key != self.tool_key.strip():
            raise ValueError('tool_key must not contain surrounding whitespace')
        if not isinstance(self.snapshot, KpiTimeseriesSnapshot):
            raise TypeError('snapshot must be KpiTimeseriesSnapshot')


# El dataclass siguiente representa un contrato de datos explícito.
@dataclass(frozen=True, slots=True)
# Esta clase delimita una responsabilidad concreta del proceso.
class KpiTimeseriesToolPublicationResult:
    tool_key: str
    publication: KpiTimeseriesPublication | None
    error: Exception | None

    @property
# Esta función conserva los contratos e invariantes declarados por el módulo.
    def successful(self) -> bool:
        return self.error is None


# Esta clase delimita una responsabilidad concreta del proceso.
class ParallelKpiTimeseriesPublisher:
# Esta función conserva los contratos e invariantes declarados por el módulo.
    def __init__(
        self,
        *,
        publishers: Mapping[str, _SnapshotPublisher],
        max_workers: int,
    ) -> None:
        if not isinstance(publishers, Mapping) or not publishers:
            raise ValueError('publishers must contain at least one tool')
        if isinstance(max_workers, bool) or not isinstance(max_workers, int) or max_workers <= 0:
            raise ValueError('max_workers must be a positive integer')
        if any(
            not callable(getattr(publisher, 'publish', None))
            for publisher in publishers.values()
        ):
            raise TypeError('publishers must provide callable publish methods')
        self._publishers = dict(publishers)
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix='kpi-timeseries',
        )
        self._closed = False

# Esta función conserva los contratos e invariantes declarados por el módulo.
    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._executor.shutdown(wait=True)

# Esta función conserva los contratos e invariantes declarados por el módulo.
    def publish(
        self,
        tasks: tuple[KpiTimeseriesPublicationTask, ...],
    ) -> tuple[KpiTimeseriesToolPublicationResult, ...]:
        if self._closed:
            raise RuntimeError('KPI timeseries publisher is closed')
        if not isinstance(tasks, tuple) or any(
            not isinstance(task, KpiTimeseriesPublicationTask) for task in tasks
        ):
            raise TypeError('tasks must contain KpiTimeseriesPublicationTask values')
        if len({task.tool_key for task in tasks}) != len(tasks):
            raise ValueError('Only one publication task per tool is allowed')
        if any(task.tool_key not in self._publishers for task in tasks):
            raise ValueError('Publication task refers to an unknown tool')
        if not tasks:
            return ()

        futures = {
            self._executor.submit(self._publish_one, task): task for task in tasks
        }
        results: list[KpiTimeseriesToolPublicationResult] = []
        for future in as_completed(futures):
            task = futures[future]
            try:
                publication = future.result()
                results.append(
                    KpiTimeseriesToolPublicationResult(
                        tool_key=task.tool_key,
                        publication=publication,
                        error=None,
                    )
                )
            except Exception as error:
                results.append(
                    KpiTimeseriesToolPublicationResult(
                        tool_key=task.tool_key,
                        publication=None,
                        error=error,
                    )
                )
        return tuple(sorted(results, key=lambda result: result.tool_key))

# Esta función conserva los contratos e invariantes declarados por el módulo.
    def _publish_one(
        self,
        task: KpiTimeseriesPublicationTask,
    ) -> KpiTimeseriesPublication:
        return self._publishers[task.tool_key].publish(task.snapshot)
