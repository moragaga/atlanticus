# Espejo pedagógico de KPI Latest Delivery paralelo por Tool: parallel.py.
from __future__ import annotations

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Protocol

from ada.kpis.delivery import KpiLatestSnapshot
from ada.processes.kpi_delivery.models import KpiLatestPublication


# Define una responsabilidad con estado o contrato propio.
class _SnapshotPublisher(Protocol):
    def publish(self, snapshot: KpiLatestSnapshot) -> KpiLatestPublication: ...


@dataclass(frozen=True, slots=True)
# Define una responsabilidad con estado o contrato propio.
class KpiLatestPublicationTask:
    tool_key: str
    snapshot: KpiLatestSnapshot

    def __post_init__(self) -> None:
        if not isinstance(self.tool_key, str) or not self.tool_key:
            raise ValueError('tool_key must be non-empty text')
        if self.tool_key != self.tool_key.strip():
            raise ValueError('tool_key must not contain surrounding whitespace')
        if not isinstance(self.snapshot, KpiLatestSnapshot):
            raise TypeError('snapshot must be KpiLatestSnapshot')


@dataclass(frozen=True, slots=True)
# Define una responsabilidad con estado o contrato propio.
class KpiLatestToolPublicationResult:
    tool_key: str
    publication: KpiLatestPublication | None
    error: Exception | None

    @property
    def successful(self) -> bool:
        return self.error is None


# Define una responsabilidad con estado o contrato propio.
class ParallelKpiLatestPublisher:
    def __init__(
        self,
        *,
        publishers: Mapping[str, _SnapshotPublisher],
        max_workers: int,
    ) -> None:
        if not isinstance(publishers, Mapping) or not publishers:
            raise ValueError('publishers must contain at least one tool')
        if (
            isinstance(max_workers, bool)
            or not isinstance(max_workers, int)
            or max_workers <= 0
        ):
            raise ValueError('max_workers must be a positive integer')
        if any(
            not callable(getattr(publisher, 'publish', None))
            for publisher in publishers.values()
        ):
            raise TypeError('publishers must provide callable publish methods')
        self._publishers = dict(publishers)
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix='kpi-latest',
        )
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._executor.shutdown(wait=True)

    def publish(
        self,
        tasks: tuple[KpiLatestPublicationTask, ...],
    ) -> tuple[KpiLatestToolPublicationResult, ...]:
        if self._closed:
            raise RuntimeError('KPI latest publisher is closed')
        if not isinstance(tasks, tuple) or any(
            not isinstance(task, KpiLatestPublicationTask) for task in tasks
        ):
            raise TypeError('tasks must contain KpiLatestPublicationTask values')
        if len({task.tool_key for task in tasks}) != len(tasks):
            raise ValueError('Only one publication task per tool is allowed')
        if any(task.tool_key not in self._publishers for task in tasks):
            raise ValueError('Publication task refers to an unknown tool')
        if not tasks:
            return ()

        future_to_task = {
            self._executor.submit(self._publish_one, task): task for task in tasks
        }
        results: list[KpiLatestToolPublicationResult] = []
        for future in as_completed(future_to_task):
            task = future_to_task[future]
            try:
                publication = future.result()
                results.append(
                    KpiLatestToolPublicationResult(
                        tool_key=task.tool_key,
                        publication=publication,
                        error=None,
                    )
                )
            except Exception as error:
                results.append(
                    KpiLatestToolPublicationResult(
                        tool_key=task.tool_key,
                        publication=None,
                        error=error,
                    )
                )
        return tuple(sorted(results, key=lambda result: result.tool_key))

    def _publish_one(
        self,
        task: KpiLatestPublicationTask,
    ) -> KpiLatestPublication:
        return self._publishers[task.tool_key].publish(task.snapshot)
