from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from ada.kpis.history import (
    KpiHistoryContractError,
    decode_history_value,
    history_definition,
    history_target,
)
from ada.processes.kpi_timeseries_delivery.errors import (
    KpiTimeseriesDeliveryRepositoryError,
)
from atlanticus.datasets.parquet import ColumnFilter, FilterOperator
from atlanticus.datasets.runtime import DatasetRuntime, DatasetRuntimeNotFoundError


class KpiTimeseriesHistoryRepository:
    def __init__(self, *, runtime: DatasetRuntime) -> None:
        if not isinstance(runtime, DatasetRuntime):
            raise TypeError('runtime must be DatasetRuntime')
        self._runtime = runtime

    def read_histories(
        self,
        *,
        keys: tuple[str, ...],
        start_utc: datetime,
        end_utc: datetime,
    ) -> dict[str, dict[datetime, Any]]:
        normalized_keys = _keys(keys)
        histories: dict[str, dict[datetime, Any]] = {key: {} for key in normalized_keys}
        if not normalized_keys:
            return histories
        filters = (
            ColumnFilter(
                column='key',
                operator=FilterOperator.IN,
                value=normalized_keys,
            ),
            ColumnFilter(
                column='timestamp_utc',
                operator=FilterOperator.GREATER_THAN,
                value=start_utc,
            ),
            ColumnFilter(
                column='timestamp_utc',
                operator=FilterOperator.LESS_THAN_OR_EQUAL,
                value=end_utc,
            ),
        )
        for day in _days(start_utc.date(), end_utc.date()):
            try:
                result = self._runtime.scan_table(
                    definition=history_definition(),
                    targets=(history_target(day),),
                    columns=('timestamp_utc', 'key', 'value'),
                    filters=filters,
                )
            except DatasetRuntimeNotFoundError:
                continue
            for row in result.table.to_pylist():
                timestamp = row.get('timestamp_utc')
                key = row.get('key')
                encoded = row.get('value')
                if not isinstance(timestamp, datetime):
                    raise KpiTimeseriesDeliveryRepositoryError(
                        'KPI history timestamp_utc is invalid'
                    )
                if not isinstance(key, str) or key not in histories:
                    raise KpiTimeseriesDeliveryRepositoryError('KPI history key is invalid')
                try:
                    histories[key][timestamp] = decode_history_value(encoded)
                except (TypeError, KpiHistoryContractError) as error:
                    raise KpiTimeseriesDeliveryRepositoryError(
                        'KPI history value is invalid'
                    ) from error
        return histories


def _keys(values: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TypeError('keys must be a tuple')
    if any(not isinstance(value, str) or not value for value in values):
        raise ValueError('keys must contain non-empty strings')
    return tuple(dict.fromkeys(values))


def _days(start: date, end: date) -> tuple[date, ...]:
    if end < start:
        return ()
    count = (end - start).days
    return tuple(start + timedelta(days=index) for index in range(count + 1))
