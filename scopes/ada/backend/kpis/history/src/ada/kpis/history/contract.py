from __future__ import annotations

from datetime import date, datetime

import pyarrow as pa

from atlanticus.datasets.layouts import SingleArtifactLayout
from atlanticus.datasets.models import (
    DatasetDefinition,
    DatasetKey,
    DatasetTarget,
    MaterializationDefinition,
)

HISTORY_SCHEMA_VERSION = 2
HISTORY_MATERIALIZATION = 'daily'
HISTORY_PARTITION_DIMENSIONS = ('year', 'month', 'day')
HISTORY_KEY_COLUMNS = ('timestamp_utc', 'key')
HISTORY_ORDER_COLUMNS = ('timestamp_utc', 'key')

_HISTORY_DEFINITION = DatasetDefinition(
    key=DatasetKey(namespace=('kpis',), name='history'),
    materializations=(
        MaterializationDefinition(
            name=HISTORY_MATERIALIZATION,
            layout=SingleArtifactLayout(),
            partition_dimensions=HISTORY_PARTITION_DIMENSIONS,
            route_segments=(),
        ),
    ),
)
_ERROR_HISTORY_DEFINITION = DatasetDefinition(
    key=DatasetKey(namespace=('kpis',), name='error-history'),
    materializations=(
        MaterializationDefinition(
            name=HISTORY_MATERIALIZATION,
            layout=SingleArtifactLayout(),
            partition_dimensions=HISTORY_PARTITION_DIMENSIONS,
            route_segments=(),
        ),
    ),
)
_HISTORY_SCHEMA = pa.schema(
    (
        pa.field('timestamp_utc', pa.timestamp('us', tz='UTC'), nullable=False),
        pa.field('key', pa.string(), nullable=False),
        pa.field('status', pa.string(), nullable=False),
        pa.field('value_kind', pa.string(), nullable=False),
        pa.field('value_type', pa.string(), nullable=True),
        pa.field('value', pa.string(), nullable=True),
        pa.field('parsed_value', pa.string(), nullable=True),
    )
)
_ERROR_HISTORY_SCHEMA = pa.schema(
    (
        pa.field('timestamp_utc', pa.timestamp('us', tz='UTC'), nullable=False),
        pa.field('key', pa.string(), nullable=False),
        pa.field('error', pa.string(), nullable=False),
    )
)


def history_definition() -> DatasetDefinition:
    return _HISTORY_DEFINITION


def error_history_definition() -> DatasetDefinition:
    return _ERROR_HISTORY_DEFINITION


def history_schema() -> pa.Schema:
    return _HISTORY_SCHEMA


def error_history_schema() -> pa.Schema:
    return _ERROR_HISTORY_SCHEMA


def history_target(day: date) -> DatasetTarget:
    return _daily_target(_HISTORY_DEFINITION, day)


def error_history_target(day: date) -> DatasetTarget:
    return _daily_target(_ERROR_HISTORY_DEFINITION, day)


def _daily_target(definition: DatasetDefinition, day: date) -> DatasetTarget:
    if not isinstance(day, date) or isinstance(day, datetime):
        raise TypeError('day must be a date')
    return definition.resolve_target(
        materialization=HISTORY_MATERIALIZATION,
        partition={
            'year': f'{day.year:04d}',
            'month': f'{day.month:02d}',
            'day': f'{day.day:02d}',
        },
    )
