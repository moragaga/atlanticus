from datetime import UTC, datetime

import pytest

from ada.processes.kpi_timeseries_delivery.errors import KpiTimeseriesDeliveryRepositoryError
from ada.processes.kpi_timeseries_delivery.history import KpiTimeseriesHistoryRepository


class Table:
    def __init__(self, rows):
        self._rows = rows

    def to_pylist(self):
        return list(self._rows)


class ScanResult:
    def __init__(self, rows):
        self.table = Table(rows)


class RuntimeStub:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def scan_table(self, **kwargs):
        self.calls.append(kwargs)
        return ScanResult(self.rows)


def repository(rows):
    value = object.__new__(KpiTimeseriesHistoryRepository)
    value._runtime = RuntimeStub(rows)
    return value


def test_history_reader_preserves_text_one_and_float_contract() -> None:
    timestamp = datetime(2026, 9, 1, 12, 2, tzinfo=UTC)
    repo = repository(
        [
            {
                'timestamp_utc': timestamp,
                'key': 'state',
                'status': 'ok',
                'value_kind': 'value',
                'value_type': 'text',
                'value': '1',
            },
            {
                'timestamp_utc': timestamp,
                'key': 'f80',
                'status': 'ok',
                'value_kind': 'value',
                'value_type': 'float',
                'value': '4.29',
            },
        ]
    )
    histories = repo.read_histories(
        keys=('state', 'f80'),
        start_utc=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        end_utc=datetime(2026, 9, 1, 12, 4, tzinfo=UTC),
    )
    assert histories['state'].value_type == 'text'
    assert histories['state'].values[timestamp] == '1'
    assert histories['f80'].value_type == 'float'
    assert histories['f80'].values[timestamp] == '4.29'


def test_missing_row_keeps_series_type_without_creating_point() -> None:
    timestamp = datetime(2026, 9, 1, 12, 2, tzinfo=UTC)
    repo = repository(
        [
            {
                'timestamp_utc': timestamp,
                'key': 'state',
                'status': 'missing',
                'value_kind': 'value',
                'value_type': 'text',
                'value': None,
            }
        ]
    )
    histories = repo.read_histories(
        keys=('state',),
        start_utc=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        end_utc=datetime(2026, 9, 1, 12, 4, tzinfo=UTC),
    )
    assert histories['state'].value_type == 'text'
    assert dict(histories['state'].values) == {}


def test_history_reader_rejects_json_series() -> None:
    timestamp = datetime(2026, 9, 1, 12, 2, tzinfo=UTC)
    repo = repository(
        [
            {
                'timestamp_utc': timestamp,
                'key': 'payload',
                'status': 'ok',
                'value_kind': 'json',
                'value_type': None,
                'value': '{"a":1}',
            }
        ]
    )
    with pytest.raises(KpiTimeseriesDeliveryRepositoryError, match='not timeseries-compatible'):
        repo.read_histories(
            keys=('payload',),
            start_utc=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
            end_utc=datetime(2026, 9, 1, 12, 4, tzinfo=UTC),
        )


def test_history_reader_rejects_type_drift() -> None:
    first = datetime(2026, 9, 1, 12, 2, tzinfo=UTC)
    second = datetime(2026, 9, 1, 12, 4, tzinfo=UTC)
    repo = repository(
        [
            {
                'timestamp_utc': first,
                'key': 'metric',
                'status': 'ok',
                'value_kind': 'value',
                'value_type': 'integer',
                'value': '1',
            },
            {
                'timestamp_utc': second,
                'key': 'metric',
                'status': 'ok',
                'value_kind': 'value',
                'value_type': 'float',
                'value': '1.0',
            },
        ]
    )
    with pytest.raises(KpiTimeseriesDeliveryRepositoryError, match='remain stable'):
        repo.read_histories(
            keys=('metric',),
            start_utc=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
            end_utc=datetime(2026, 9, 1, 12, 4, tzinfo=UTC),
        )
