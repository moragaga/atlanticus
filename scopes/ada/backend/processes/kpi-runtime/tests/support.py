from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from ada.kpis.core import KpiArea, KpiCatalog, KpiMode, KpiSpec, KpiWatermark
from ada.kpis.persistence import KpiPersistence
from atlanticus.operational_data.core import DataColumn, DataColumnType, DataPartition, DataSource
from atlanticus.operational_data.planner import DataRequirementPlanner
from atlanticus.operational_data.sources import (
    DataSourceLoader,
    PiSourceProvider,
    build_current_source_registry,
)


class StaticWatermarkReader:
    def __init__(self, value: KpiWatermark | None) -> None:
        self.value = value
        self.calls = 0

    def current(self) -> KpiWatermark | None:
        self.calls += 1
        return self.value


class FrameReader:
    def __init__(self, value: float = 42.5) -> None:
        self.value = value
        self.calls = 0

    def read_frame(self, **_kwargs):
        self.calls += 1
        return pd.DataFrame(
            {
                'timestamp_utc': [datetime(2026, 8, 31, 20, 0, tzinfo=UTC)],
                'signal': [self.value],
            }
        )


class RuntimeContextStub:
    def __init__(self) -> None:
        self.iteration_facts: dict[str, object] = {}
        self.execution_facts: dict[str, object] = {}
        self.execution_counters: dict[str, float] = {}
        self.work = False
        self.cancel_checks = 0
        self.lease_checks = 0
        self.fences = 0

    def raise_if_cancelled(self) -> None:
        self.cancel_checks += 1

    def assert_lease_current(self) -> None:
        self.lease_checks += 1

    @contextmanager
    def fenced_mutation(self):
        self.fences += 1
        yield

    def mark_iteration_work(self) -> None:
        self.work = True

    def set_iteration_fact(self, key: str, value: object) -> None:
        self._validate_fact(key, value)
        self.iteration_facts[key] = value

    def set_execution_fact(self, key: str, value: object) -> None:
        self._validate_fact(key, value)
        self.execution_facts[key] = value

    def increment_execution_counter(self, key: str, amount: int | float = 1) -> None:
        self.execution_counters[key] = self.execution_counters.get(key, 0) + amount

    @staticmethod
    def _validate_fact(key: str, value: object) -> None:
        if value is None:
            raise TypeError(f'operational field {key!r} must be a scalar value')


def watermark(minute: int) -> KpiWatermark:
    return KpiWatermark(datetime(2026, 8, 31, 20, minute, tzinfo=UTC))


def simple_catalog() -> KpiCatalog:
    return KpiCatalog(
        (
            KpiSpec(
                key='test-kpi',
                area=KpiArea.GENERAL,
                mode=KpiMode.LATEST_NUMBER,
                source=DataSource.PI_INTERPOLATED,
                partition=DataPartition.LATEST,
                columns=(DataColumn('signal', DataColumnType.FLOAT),),
                decimals=1,
            ),
        )
    )


def runtime_parts(tmp_path: Path, *, catalog: KpiCatalog | None = None):
    resolved_catalog = simple_catalog() if catalog is None else catalog
    registry = build_current_source_registry(pi_source=PiSourceProvider.NOTPII)
    reader = FrameReader()
    loader = DataSourceLoader(reader=reader, registry=registry)
    plan = DataRequirementPlanner().plan({spec.key: spec.requirements for spec in resolved_catalog})
    persistence = KpiPersistence.from_runtime(volume_path=tmp_path, application='ada-test')
    return resolved_catalog, plan, loader, persistence, reader
