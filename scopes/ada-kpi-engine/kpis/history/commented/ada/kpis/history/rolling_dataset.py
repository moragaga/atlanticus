# Contrato físico del rolling aislado para evitar ciclos de imports.
from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime

import pyarrow as pa

from ada.kpis.history.errors import KpiHistoryContractError
from ada.kpis.history.rolling import (
    ROLLING_DIRECTORY,
    ROLLING_FILENAME,
    ROLLING_GRID_SECONDS,
    ROLLING_MAX_HOURS,
    ROLLING_METADATA_KEY,
    ROLLING_TIMESTAMP_COLUMN,
    KpiRollingMetadata,
)
from atlanticus.datasets.layouts import SingleArtifactLayout
from atlanticus.datasets.models import (
    DatasetDefinition,
    DatasetKey,
    DatasetTarget,
    MaterializationDefinition,
)

ROLLING_MATERIALIZATION = 'current'

# La definición física del rolling queda aislada del contrato durable.
_ROLLING_DEFINITION = DatasetDefinition(
    key=DatasetKey(namespace=('kpis',), name='rolling'),
    materializations=(
        MaterializationDefinition(
            name=ROLLING_MATERIALIZATION,
            layout=SingleArtifactLayout(
                artifact_name=ROLLING_FILENAME.removesuffix('.parquet'),
                allow_empty=True,
            ),
            route_segments=(),
        ),
    ),
    route_segments=(ROLLING_DIRECTORY,),
)


# Esta función expone una parte del contrato compartido.
def rolling_definition() -> DatasetDefinition:
    return _ROLLING_DEFINITION


# Esta función expone una parte del contrato compartido.
def rolling_target() -> DatasetTarget:
    return _ROLLING_DEFINITION.resolve_target(
        materialization=ROLLING_MATERIALIZATION,
    )

# Esta función expone una parte del contrato compartido.
def rolling_table(
    *,
    metadata: KpiRollingMetadata,
    points: Mapping[datetime, Mapping[str, str]],
) -> pa.Table:
    if not isinstance(metadata, KpiRollingMetadata):
        raise TypeError('metadata must be KpiRollingMetadata')
    if not isinstance(points, Mapping):
        raise TypeError('points must be a mapping')
    normalized: dict[datetime, dict[str, str]] = {}
    for timestamp, row in points.items():
        resolved_timestamp = _rolling_timestamp(timestamp)
        if not isinstance(row, Mapping) or not row:
            raise KpiHistoryContractError(
                'KPI rolling physical row must contain observed values'
            )
        values: dict[str, str] = {}
        for key, value in row.items():
            if key not in metadata.value_types:
                raise KpiHistoryContractError(
                    'KPI rolling physical row contains an unknown key'
                )
            if not isinstance(value, str):
                raise KpiHistoryContractError(
                    'KPI rolling physical value must be text'
                )
            values[key] = value
        normalized[resolved_timestamp] = values
    timestamps = sorted(normalized)
    actual_start = None if not timestamps else timestamps[0]
    actual_end = None if not timestamps else timestamps[-1]
    if (
        metadata.coverage_start_utc != actual_start
        or metadata.coverage_end_utc != actual_end
    ):
        raise KpiHistoryContractError(
            'KPI rolling coverage metadata does not match points'
        )
    keys = tuple(metadata.value_types)
    arrays = [pa.array(timestamps, type=pa.timestamp('us', tz='UTC'))]
    arrays.extend(
        pa.array(
            [normalized[timestamp].get(key) for timestamp in timestamps],
            type=pa.string(),
        )
        for key in keys
    )
    fields = [
        pa.field(
            ROLLING_TIMESTAMP_COLUMN,
            pa.timestamp('us', tz='UTC'),
            nullable=False,
        ),
        *(pa.field(key, pa.string(), nullable=True) for key in keys),
    ]
    schema = pa.schema(fields).with_metadata(
        {ROLLING_METADATA_KEY.encode('utf-8'): metadata.to_bytes()}
    )
    return pa.Table.from_arrays(arrays, schema=schema)


# Esta función expone una parte del contrato compartido.
def rolling_metadata_from_schema(schema: pa.Schema) -> KpiRollingMetadata:
    if not isinstance(schema, pa.Schema):
        raise TypeError('schema must be pyarrow.Schema')
    metadata_bytes = (schema.metadata or {}).get(
        ROLLING_METADATA_KEY.encode('utf-8')
    )
    if metadata_bytes is None:
        raise KpiHistoryContractError('KPI rolling metadata is missing')
    metadata = KpiRollingMetadata.from_bytes(metadata_bytes)
    _validate_rolling_schema(
        schema=schema,
        keys=tuple(metadata.value_types),
    )
    return metadata


# Esta función expone una parte del contrato compartido.
def rolling_state_from_table(
    table: pa.Table,
) -> tuple[KpiRollingMetadata, dict[datetime, dict[str, str]]]:
    if not isinstance(table, pa.Table):
        raise TypeError('table must be pyarrow.Table')
    metadata = rolling_metadata_from_schema(table.schema)
    points: dict[datetime, dict[str, str]] = {}
    previous: datetime | None = None
    for row in table.to_pylist():
        timestamp = _rolling_timestamp(row.get(ROLLING_TIMESTAMP_COLUMN))
        if previous is not None and timestamp <= previous:
            raise KpiHistoryContractError(
                'KPI rolling timestamps must be strictly increasing'
            )
        values: dict[str, str] = {}
        for key in metadata.value_types:
            value = row.get(key)
            if value is not None and not isinstance(value, str):
                raise KpiHistoryContractError(
                    'KPI rolling physical value is invalid'
                )
            if value is not None:
                values[key] = value
        if not values:
            raise KpiHistoryContractError(
                'KPI rolling must not persist empty physical rows'
            )
        points[timestamp] = values
        previous = timestamp
    actual_start = None if not points else min(points)
    actual_end = None if not points else max(points)
    if (
        metadata.coverage_start_utc != actual_start
        or metadata.coverage_end_utc != actual_end
    ):
        raise KpiHistoryContractError(
            'KPI rolling coverage metadata is invalid'
        )
    cutoff = metadata.watermark_utc.timestamp() - (ROLLING_MAX_HOURS * 3600)
    if any(
        timestamp.timestamp() <= cutoff
        or timestamp > metadata.watermark_utc
        for timestamp in points
    ):
        raise KpiHistoryContractError(
            'KPI rolling coverage is outside its horizon'
        )
    return metadata, points


# Esta función expone una parte del contrato compartido.
def rolling_projection_from_table(
    table: pa.Table,
    *,
    metadata: KpiRollingMetadata,
    keys: Iterable[str],
) -> dict[str, dict[datetime, str]]:
    if not isinstance(table, pa.Table):
        raise TypeError('table must be pyarrow.Table')
    if not isinstance(metadata, KpiRollingMetadata):
        raise TypeError('metadata must be KpiRollingMetadata')
    if isinstance(keys, str | bytes):
        raise TypeError('keys must be an iterable of KPI keys')
    try:
        resolved_keys = tuple(keys)
    except TypeError as error:
        raise TypeError('keys must be an iterable of KPI keys') from error
    if len(set(resolved_keys)) != len(resolved_keys):
        raise KpiHistoryContractError(
            'KPI rolling projection keys must be unique'
        )
    if any(
        not isinstance(key, str)
        or not key
        or key != key.strip()
        or key not in metadata.value_types
        for key in resolved_keys
    ):
        raise KpiHistoryContractError(
            'KPI rolling projection key is invalid'
        )
    _validate_rolling_schema(
        schema=table.schema,
        keys=resolved_keys,
    )
    values_by_key: dict[str, dict[datetime, str]] = {
        key: {} for key in resolved_keys
    }
    previous: datetime | None = None
    for row in table.to_pylist():
        timestamp = _rolling_timestamp(row.get(ROLLING_TIMESTAMP_COLUMN))
        if previous is not None and timestamp <= previous:
            raise KpiHistoryContractError(
                'KPI rolling projection timestamps must be strictly increasing'
            )
        for key in resolved_keys:
            value = row.get(key)
            if value is None:
                continue
            if not isinstance(value, str):
                raise KpiHistoryContractError(
                    'KPI rolling projection value is invalid'
                )
            values_by_key[key][timestamp] = value
        previous = timestamp
    return values_by_key


# Esta función expone una parte del contrato compartido.
def _validate_rolling_schema(
    *,
    schema: pa.Schema,
    keys: tuple[str, ...],
) -> None:
    expected = [ROLLING_TIMESTAMP_COLUMN, *keys]
    if schema.names != expected:
        raise KpiHistoryContractError('KPI rolling columns are invalid')
    timestamp_field = schema.field(ROLLING_TIMESTAMP_COLUMN)
    if (
        timestamp_field.type != pa.timestamp('us', tz='UTC')
        or timestamp_field.nullable
    ):
        raise KpiHistoryContractError(
            'KPI rolling timestamp schema is invalid'
        )
    for key in keys:
        field = schema.field(key)
        if field.type != pa.string() or not field.nullable:
            raise KpiHistoryContractError(
                f'KPI rolling value schema is invalid for {key}'
            )


# Esta función expone una parte del contrato compartido.
def _rolling_timestamp(value: object) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
        or value.microsecond != 0
        or int(value.timestamp()) % ROLLING_GRID_SECONDS != 0
    ):
        raise KpiHistoryContractError(
            f'KPI rolling timestamp must align to '
            f'the {ROLLING_GRID_SECONDS}-second grid'
        )
    return value
