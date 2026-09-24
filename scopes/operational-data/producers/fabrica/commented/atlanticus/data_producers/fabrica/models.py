# Espejo pedagógico: misma ejecución y contratos que el archivo productivo.
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from re import Pattern
from zoneinfo import ZoneInfo

from atlanticus.data_producers.fabrica.contracts import (
    FabricaDatasetDefinition,
    FabricaMetricDefinition,
    validate_dataset_catalog,
)


@dataclass(frozen=True, slots=True)
# Contrato de FabricaSourceBlob.
class FabricaSourceBlob:
    name: str
    source_file_timestamp_utc: datetime
    size: int | None
    etag: str | None
    last_modified_utc: datetime | None


@dataclass(frozen=True, slots=True)
# Define el flujo reutilizable que recibe cada proceso sin requerir el otro.
class FabricaStreamDefinition:
    stream_key: str
    source_prefix: str
    source_filename_pattern: Pattern[str]
    output_route_segment: str
    datasets: tuple[FabricaDatasetDefinition, ...]
    source_partition_timezone_name: str = 'America/Santiago'
    source_file_timezone_name: str = 'UTC'
    report_unknown_source_values: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.stream_key, str) or not self.stream_key.strip():
            raise ValueError('stream_key is required')
        if not self.source_prefix.strip().strip('/'):
            raise ValueError('source_prefix is required')
        if not self.output_route_segment.strip().strip('/'):
            raise ValueError('output_route_segment is required')
        datasets = tuple(self.datasets)
        validate_dataset_catalog(datasets=datasets)
        object.__setattr__(self, 'datasets', datasets)
        ZoneInfo(self.source_partition_timezone_name)
        ZoneInfo(self.source_file_timezone_name)

    @property
    def metrics(self) -> tuple[FabricaMetricDefinition, ...]:
        ordered: dict[str, FabricaMetricDefinition] = {}
        for dataset in self.datasets:
            for metric in dataset.metrics:
                ordered.setdefault(metric.id_kpi, metric)
        return tuple(ordered.values())

    def source_day_prefix(self, value: datetime) -> str:
        normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        local_date: date = normalized.astimezone(ZoneInfo(self.source_partition_timezone_name)).date()
        prefix = self.source_prefix.strip().strip('/')
        return f'{prefix}/year={local_date:%Y}/month={local_date:%m}/day={local_date:%d}/'


# Convierte la fecha codificada en el nombre usando la zona de archivo declarada.
def parse_source_file_timestamp(*, definition: FabricaStreamDefinition, blob_name: str) -> datetime | None:
    match = definition.source_filename_pattern.search(blob_name)
    if match is None:
        return None
    try:
        parsed = datetime.strptime(match.group('file_timestamp'), '%Y%m%d%H%M%S')
    except (IndexError, ValueError):
        return None
    return parsed.replace(tzinfo=ZoneInfo(definition.source_file_timezone_name)).astimezone(UTC)
