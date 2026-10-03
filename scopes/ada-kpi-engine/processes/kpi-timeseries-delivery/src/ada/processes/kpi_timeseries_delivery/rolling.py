from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Protocol

from ada.kpis.delivery import KpiTimeseriesHistory
from ada.kpis.history import (
    ROLLING_TIMESTAMP_COLUMN,
    KpiHistorianAuthority,
    KpiHistoryContractError,
)
from ada.kpis.history.dataset import (
    rolling_definition,
    rolling_metadata_from_schema,
    rolling_projection_from_table,
    rolling_schema_token,
    rolling_table_schema_token,
    rolling_target,
)
from ada.processes.kpi_timeseries_delivery.errors import (
    KpiTimeseriesDeliveryRepositoryError,
)
from atlanticus.datasets.runtime import (
    ColumnFilter,
    DatasetRuntimeNotFoundError,
    DatasetRuntimeReadError,
    DatasetRuntimeValidationError,
    FilterOperator,
)


class _RollingRuntime(Protocol):
    def read_schema(self, *, definition, target): ...

    def scan_table(
        self,
        *,
        definition,
        targets,
        columns=None,
        filters=(),
    ): ...


@dataclass(frozen=True, slots=True)
class KpiTimeseriesRollingSlice:
    watermark_utc: datetime
    historian_revision: str
    histories: Mapping[str, KpiTimeseriesHistory]

    def __post_init__(self) -> None:
        if not isinstance(self.watermark_utc, datetime):
            raise TypeError('watermark_utc must be datetime')
        if self.watermark_utc.tzinfo is None or self.watermark_utc.utcoffset() is None:
            raise ValueError('watermark_utc must be timezone-aware')
        if not isinstance(self.historian_revision, str) or not self.historian_revision:
            raise ValueError('historian_revision must be non-empty text')
        if not isinstance(self.histories, Mapping):
            raise TypeError('histories must be a mapping')
        object.__setattr__(
            self,
            'watermark_utc',
            self.watermark_utc.astimezone(UTC),
        )
        object.__setattr__(
            self,
            'histories',
            MappingProxyType(dict(self.histories)),
        )


class KpiTimeseriesRollingRepository:
    def __init__(self, *, runtime: _RollingRuntime) -> None:
        for method_name in ('read_schema', 'scan_table'):
            if not callable(getattr(runtime, method_name, None)):
                raise TypeError(f'runtime must provide a callable {method_name} method')
        self._runtime = runtime

    def read(
        self,
        *,
        authority: KpiHistorianAuthority,
        keys: tuple[str, ...],
        start_utc: datetime,
        end_utc: datetime,
    ) -> KpiTimeseriesRollingSlice:
        if not isinstance(authority, KpiHistorianAuthority):
            raise TypeError('authority must be KpiHistorianAuthority')
        normalized_keys = _keys(keys)
        start = _utc_datetime(start_utc, 'start_utc')
        end = _utc_datetime(end_utc, 'end_utc')
        if start >= end:
            raise KpiTimeseriesDeliveryRepositoryError(
                'Timeseries rolling start_utc must be before end_utc'
            )
        if end > authority.watermark_utc:
            raise KpiTimeseriesDeliveryRepositoryError(
                'Timeseries rolling end_utc must not exceed historian authority'
            )

        definition = rolling_definition()
        target = rolling_target()
        try:
            schema = self._runtime.read_schema(
                definition=definition,
                target=target,
            )
            schema_token = rolling_schema_token(schema)
            metadata = rolling_metadata_from_schema(schema)
        except DatasetRuntimeNotFoundError as error:
            raise KpiTimeseriesDeliveryRepositoryError(
                'KPI historian rolling file was not found'
            ) from error
        except (
            KpiHistoryContractError,
            DatasetRuntimeReadError,
            DatasetRuntimeValidationError,
        ) as error:
            raise KpiTimeseriesDeliveryRepositoryError(
                'KPI historian rolling file is invalid'
            ) from error

        if (
            metadata.watermark_utc != authority.watermark_utc
            or metadata.historian_revision != authority.revision
        ):
            raise KpiTimeseriesDeliveryRepositoryError(
                'KPI historian rolling is not coherent with historian authority'
            )

        existing_keys = tuple(key for key in normalized_keys if key in metadata.value_types)
        if not existing_keys:
            return KpiTimeseriesRollingSlice(
                watermark_utc=metadata.watermark_utc,
                historian_revision=metadata.historian_revision,
                histories={},
            )

        try:
            result = self._runtime.scan_table(
                definition=definition,
                targets=(target,),
                columns=(
                    ROLLING_TIMESTAMP_COLUMN,
                    *existing_keys,
                ),
                filters=(
                    ColumnFilter(
                        column=ROLLING_TIMESTAMP_COLUMN,
                        operator=FilterOperator.GREATER_THAN,
                        value=start,
                    ),
                    ColumnFilter(
                        column=ROLLING_TIMESTAMP_COLUMN,
                        operator=FilterOperator.LESS_THAN_OR_EQUAL,
                        value=end,
                    ),
                ),
            )
            if rolling_table_schema_token(result.table) != schema_token:
                raise KpiTimeseriesDeliveryRepositoryError(
                    'KPI historian rolling changed during read'
                )
            values_by_key = rolling_projection_from_table(
                result.table,
                metadata=metadata,
                keys=existing_keys,
            )
        except (
            KpiHistoryContractError,
            DatasetRuntimeNotFoundError,
            DatasetRuntimeReadError,
            DatasetRuntimeValidationError,
        ) as error:
            raise KpiTimeseriesDeliveryRepositoryError(
                'Could not read KPI historian rolling data'
            ) from error

        histories = {
            key: KpiTimeseriesHistory(
                value_type=metadata.value_types[key],
                values=values_by_key[key],
            )
            for key in existing_keys
        }
        return KpiTimeseriesRollingSlice(
            watermark_utc=metadata.watermark_utc,
            historian_revision=metadata.historian_revision,
            histories=histories,
        )


def _keys(values: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TypeError('keys must be tuple')
    if any(not isinstance(value, str) or not value or value != value.strip() for value in values):
        raise ValueError('keys must contain non-empty trimmed strings')
    return tuple(dict.fromkeys(values))


def _utc_datetime(
    value: datetime,
    field_name: str,
) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f'{field_name} must be datetime')
    if value.tzinfo is None or value.utcoffset() is None:
        raise KpiTimeseriesDeliveryRepositoryError(f'{field_name} must be timezone-aware')
    if value.microsecond != 0:
        raise KpiTimeseriesDeliveryRepositoryError(f'{field_name} must be aligned to whole seconds')
    return value.astimezone(UTC)
