# Composición física exclusiva de Alarm Engine sobre los contratos de Operational Data.
# Registra todas las fuentes y particiones CURRENT con build_current_source_registry.
# El routing se resuelve a demanda; ninguna fuente no solicitada provoca lecturas.
# Las lecturas temporales aplican filtros en DatasetRuntime y LoadedDataSources
# recorta luego las columnas y ventanas específicas de cada alarma.
# Meteodata y Fábrica KPI quedan fuera porque aún no tienen bindings CURRENT.

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from ada_command_center.processes.alarms_runtime.source_adapter import AlarmDataSourceAdapter
from atlanticus.datasets.parquet import ColumnFilter, FilterOperator, ParquetDatasetStore
from atlanticus.datasets.runtime import (
    DatasetRuntime,
    DatasetRuntimeNotFoundError,
    DatasetRuntimeReadError,
    DatasetRuntimeValidationError,
)
from atlanticus.operational_data.sources import (
    DataSourceApplications,
    DataSourceLoader,
    DataSourceReadError,
    DataSourceRegistry,
    PiSourceProvider,
    build_current_source_registry,
)

RuntimeFactory = Callable[[Path], DatasetRuntime]


def _runtime_factory(root: Path) -> DatasetRuntime:
    return DatasetRuntime(store=ParquetDatasetStore(root=root))


class AlarmRoutedDatasetReader:
    def __init__(
        self,
        *,
        volume_path: Path,
        registry: DataSourceRegistry,
        applications: DataSourceApplications,
        runtime_factory: RuntimeFactory = _runtime_factory,
    ) -> None:
        if not isinstance(volume_path, Path) or not volume_path.is_absolute():
            raise ValueError('volume_path must be an absolute Path')
        if not isinstance(registry, DataSourceRegistry):
            raise TypeError('registry must be DataSourceRegistry')
        if not isinstance(applications, DataSourceApplications):
            raise TypeError('applications must be DataSourceApplications')
        if not callable(runtime_factory):
            raise TypeError('runtime_factory must be callable')
        sources_by_dataset = {}
        for source in registry.sources:
            identifier = registry.get(source).definition.key.identifier
            if identifier in sources_by_dataset:
                raise ValueError(f'{identifier}: multiple registered sources share a dataset key')
            sources_by_dataset[identifier] = source
        self._volume_path = volume_path
        self._applications = applications
        self._sources_by_dataset = sources_by_dataset
        self._runtime_factory = runtime_factory
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
            source = self._sources_by_dataset[identifier]
        except KeyError as error:
            raise DataSourceReadError(
                f'{identifier}: dataset has no Alarm Engine source binding'
            ) from error
        application = self._applications.application_for(source)
        runtime = self._runtimes.get(application)
        if runtime is None:
            runtime = self._runtime_factory(self._volume_path / application / 'datasets')
            self._runtimes[application] = runtime
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


def _time_filters(
    *,
    timestamp_column: str | None,
    start_utc: datetime | None,
    end_utc: datetime | None,
) -> tuple[ColumnFilter, ...]:
    if timestamp_column is None:
        if start_utc is not None or end_utc is not None:
            raise DataSourceReadError('timestamp_column is required for time-bounded reading')
        return ()
    filters = []
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


def build_alarm_source_adapter(
    *,
    volume_path: Path,
    pi_source: PiSourceProvider,
    applications: DataSourceApplications,
    runtime_factory: RuntimeFactory = _runtime_factory,
) -> AlarmDataSourceAdapter:
    registry = build_current_source_registry(pi_source=pi_source)
    reader = AlarmRoutedDatasetReader(
        volume_path=volume_path,
        registry=registry,
        applications=applications,
        runtime_factory=runtime_factory,
    )
    return AlarmDataSourceAdapter(source_loader=DataSourceLoader(reader=reader, registry=registry))


# Convertimos valores puros de configuración en contratos físicos dentro de la frontera.
def build_configured_alarm_source_adapter(
    *,
    volume_path: Path,
    pi_source: str,
    pi_application: str,
    dispatch_application: str | None,
    blockgrade_application: str | None,
    remanentes_application: str | None,
    fabrica_planes_application: str | None,
) -> AlarmDataSourceAdapter:
    return build_alarm_source_adapter(
        volume_path=volume_path,
        pi_source=PiSourceProvider(pi_source),
        applications=DataSourceApplications(
            pi=pi_application,
            dispatch=dispatch_application,
            blockgrade=blockgrade_application,
            remanentes=remanentes_application,
            fabrica_planes=fabrica_planes_application,
        ),
    )
