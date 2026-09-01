from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path

from ada.processes.kpi_runtime.errors import KpiRuntimeDataError
from atlanticus.datasets.parquet import ColumnFilter, FilterOperator, ParquetDatasetStore
from atlanticus.datasets.runtime import (
    DatasetRuntime,
    DatasetRuntimeNotFoundError,
    DatasetRuntimeReadError,
    DatasetRuntimeValidationError,
)
from atlanticus.operational_data.core import DataSource
from atlanticus.operational_data.sources import (
    DataSourceApplications,
    DataSourceReadError,
    DataSourceRegistry,
)

RuntimeFactory = Callable[[Path], DatasetRuntime]


class RoutedDatasetSourceReader:
    def __init__(
        self,
        *,
        volume_path: str | Path,
        applications: DataSourceApplications,
        registry: DataSourceRegistry,
        sources: Iterable[DataSource],
        runtime_factory: RuntimeFactory | None = None,
    ) -> None:
        self._volume_path = _absolute_path(volume_path)
        if not isinstance(applications, DataSourceApplications):
            raise TypeError('applications must be DataSourceApplications')
        if not isinstance(registry, DataSourceRegistry):
            raise TypeError('registry must be DataSourceRegistry')
        resolved_sources = tuple(sources)
        if any(not isinstance(source, DataSource) for source in resolved_sources):
            raise TypeError('sources must contain DataSource values')
        self._runtime_factory = _runtime_factory if runtime_factory is None else runtime_factory
        if not callable(self._runtime_factory):
            raise TypeError('runtime_factory must be callable')
        self._applications_by_dataset = _dataset_routes(registry, applications, resolved_sources)
        self._runtimes: dict[str, DatasetRuntime] = {}

    def read_frame(
        self,
        *,
        definition,
        target,
        projection_schema,
        timestamp_column: str | None = None,
        start_utc: datetime | None = None,
        end_utc: datetime | None = None,
    ):
        identifier = definition.key.identifier
        try:
            application = self._applications_by_dataset[identifier]
        except KeyError as error:
            raise KpiRuntimeDataError(
                f'{identifier}: dataset has no configured application route'
            ) from error
        runtime = self._runtime_for(application)
        filters = _time_filters(
            timestamp_column=timestamp_column,
            start_utc=start_utc,
            end_utc=end_utc,
        )
        try:
            result = runtime.scan_dataframe(
                definition=definition,
                targets=(target,),
                projection_schema=projection_schema,
                filters=filters,
            )
        except DatasetRuntimeNotFoundError:
            return None
        except (DatasetRuntimeReadError, DatasetRuntimeValidationError) as error:
            raise DataSourceReadError(f'{target.identifier}: dataset source read failed') from error
        dataframe = getattr(result, 'dataframe', None)
        if dataframe is None:
            raise DataSourceReadError(f'{target.identifier}: dataset runtime returned invalid data')
        return dataframe

    def _runtime_for(self, application: str) -> DatasetRuntime:
        runtime = self._runtimes.get(application)
        if runtime is None:
            runtime = self._runtime_factory(self._volume_path / application / 'datasets')
            self._runtimes[application] = runtime
        return runtime


def _dataset_routes(
    registry: DataSourceRegistry,
    applications: DataSourceApplications,
    sources: tuple[DataSource, ...],
) -> dict[str, str]:
    routes: dict[str, str] = {}
    for source in sources:
        binding = registry.get(source)
        identifier = binding.definition.key.identifier
        application = applications.application_for(source)
        existing = routes.get(identifier)
        if existing is not None and existing != application:
            raise KpiRuntimeDataError(f'{identifier}: dataset routes to multiple applications')
        routes[identifier] = application
    return routes


def _runtime_factory(dataset_root: Path) -> DatasetRuntime:
    return DatasetRuntime(store=ParquetDatasetStore(root=dataset_root))


def _time_filters(
    *,
    timestamp_column: str | None,
    start_utc: datetime | None,
    end_utc: datetime | None,
) -> tuple[ColumnFilter, ...]:
    if timestamp_column is None:
        if start_utc is not None or end_utc is not None:
            raise KpiRuntimeDataError(
                'timestamp_column is required when a time boundary is provided'
            )
        return ()
    filters: list[ColumnFilter] = []
    if start_utc is not None:
        filters.append(
            ColumnFilter(
                column=timestamp_column,
                operator=FilterOperator.GREATER_THAN_OR_EQUAL,
                value=start_utc,
            )
        )
    if end_utc is not None:
        filters.append(
            ColumnFilter(
                column=timestamp_column,
                operator=FilterOperator.LESS_THAN_OR_EQUAL,
                value=end_utc,
            )
        )
    return tuple(filters)


def _absolute_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise KpiRuntimeDataError('volume_path must be an absolute path')
    return path
