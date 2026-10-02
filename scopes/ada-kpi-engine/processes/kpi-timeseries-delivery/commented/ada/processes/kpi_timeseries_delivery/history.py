# Repositorio histórico de Timeseries; exige VALUE tipado, conserva ausencia y rechaza drift o JSON.
from __future__ import annotations

from datetime import date, datetime, timedelta

from ada.kpis.delivery import KpiTimeseriesHistory
from ada.kpis.history import history_definition, history_target
from ada.processes.kpi_timeseries_delivery.errors import KpiTimeseriesDeliveryRepositoryError
from atlanticus.datasets.parquet import ColumnFilter, FilterOperator
from atlanticus.datasets.runtime import DatasetRuntime, DatasetRuntimeNotFoundError

_VALUE_TYPES = frozenset({'text', 'integer', 'float', 'boolean'})
_STATUSES = frozenset({'ok', 'missing', 'error'})


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
    ) -> dict[str, KpiTimeseriesHistory]:
        normalized_keys = _keys(keys)
        if not normalized_keys:
            return {}
        points: dict[str, dict[datetime, str]] = {key: {} for key in normalized_keys}
        value_types: dict[str, str] = {}
        filters = (
            ColumnFilter(column='key', operator=FilterOperator.IN, value=normalized_keys),
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
                    columns=(
                        'timestamp_utc',
                        'key',
                        'status',
                        'value_kind',
                        'value_type',
                        'value',
                    ),
                    filters=filters,
                )
            except DatasetRuntimeNotFoundError:
                continue
            for row in result.table.to_pylist():
                timestamp = row.get('timestamp_utc')
                key = row.get('key')
                status = row.get('status')
                value_kind = row.get('value_kind')
                value_type = row.get('value_type')
                value = row.get('value')
                if not isinstance(timestamp, datetime):
                    raise KpiTimeseriesDeliveryRepositoryError(
                        'KPI history timestamp_utc is invalid'
                    )
                if not isinstance(key, str) or key not in points:
                    raise KpiTimeseriesDeliveryRepositoryError('KPI history key is invalid')
                if status not in _STATUSES:
                    raise KpiTimeseriesDeliveryRepositoryError('KPI history status is invalid')
                if value_kind == 'json':
                    raise KpiTimeseriesDeliveryRepositoryError(
                        'JSON KPI history is not timeseries-compatible'
                    )
                if value_kind != 'value':
                    raise KpiTimeseriesDeliveryRepositoryError('KPI history value_kind is invalid')
                if not isinstance(value_type, str) or value_type not in _VALUE_TYPES:
                    raise KpiTimeseriesDeliveryRepositoryError(
                        'KPI history value_type is invalid'
                    )
                previous_type = value_types.setdefault(key, value_type)
                if previous_type != value_type:
                    raise KpiTimeseriesDeliveryRepositoryError(
                        'KPI history value_type must remain stable within a series'
                    )
                if status != 'ok':
                    continue
                if not isinstance(value, str):
                    raise KpiTimeseriesDeliveryRepositoryError('KPI history value is invalid')
                points[key][timestamp] = value
        return {
            key: KpiTimeseriesHistory(value_type=value_types[key], values=points[key])
            for key in normalized_keys
            if key in value_types
        }


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
