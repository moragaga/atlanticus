from datetime import UTC, datetime
from types import SimpleNamespace

import pyarrow as pa

from atlanticus.data_producers.meteodata.materialization import (
    DATA_DATASET,
    PROJECTION_DATASET,
    MeteodataMaterializer,
)
from atlanticus.data_producers.meteodata.models import HM, HM3, Measurement, Projection
from atlanticus.datasets.runtime import DatasetRuntimeNotFoundError


class MemoryRuntime:
    def __init__(self):
        self.tables = {}
        self.writes = []

    def read_table(self, *, definition, target):
        try:
            return SimpleNamespace(table=self.tables[target.identifier])
        except KeyError:
            raise DatasetRuntimeNotFoundError('target not published') from None

    def replace(self, *, definition, target, data):
        self.tables[target.identifier] = data
        self.writes.append(('replace', target.identifier, data.num_rows))

    def merge(self, *, definition, target, data, key_columns, order_by):
        assert key_columns == ('timestamp',)
        assert order_by == ('timestamp',)
        previous = self.tables.get(target.identifier)
        rows = {} if previous is None else {row['timestamp']: row for row in previous.to_pylist()}
        rows.update({row['timestamp']: row for row in data.to_pylist()})
        self.tables[target.identifier] = pa.Table.from_pylist(
            [rows[t] for t in sorted(rows)],
            schema=data.schema,
        )
        self.writes.append(('merge', target.identifier, data.num_rows))


class Context:
    def raise_if_cancelled(self):
        pass


def test_projection_replaces_only_after_any_of_its_fields_changes():
    runtime = MemoryRuntime()
    materializer = MeteodataMaterializer(runtime=runtime)
    timestamp = datetime(2026, 9, 25, 23, 30, tzinfo=UTC)
    first = Projection(timestamp, 35.0, 36.0, True)
    assert materializer.publish_projection(projection=first, context=Context())
    assert not materializer.publish_projection(projection=first, context=Context())
    assert materializer.publish_projection(
        projection=Projection(timestamp, 35.0, 37.0, True), context=Context()
    )
    target = PROJECTION_DATASET.resolve_target(materialization='latest')
    row = runtime.tables[target.identifier].to_pylist()[0]
    assert list(row) == ['timestamp', 'promedio_dia_mp10', 'proyeccion_mp10', 'monitoreo_oficial']
    assert row['timestamp'] == timestamp
    assert row['proyeccion_mp10'] == 37.0
    assert [item[0] for item in runtime.writes] == ['replace', 'replace']


def test_daily_merges_across_utc_midnight_and_late_station_arrivals():
    runtime = MemoryRuntime()
    materializer = MeteodataMaterializer(runtime=runtime)
    early = datetime(2026, 9, 25, 23, 50, tzinfo=UTC)
    late = datetime(2026, 9, 26, 0, 0, tzinfo=UTC)
    first_batch = (
        Measurement(early, HM3, 'mp10', 42.0),
        Measurement(late, HM3, 'mp10', 50.0),
    )
    assert materializer.publish_data(measurements=first_batch, context=Context()) == 2
    assert materializer.publish_data(measurements=first_batch, context=Context()) == 0
    delayed_hm = (
        Measurement(early, HM, 'mp10', 41.0),
        Measurement(early, HM, 'vel', 2.0),
        Measurement(late, HM, 'dir', 190.0),
    )
    assert materializer.publish_data(measurements=delayed_hm, context=Context()) == 2
    day1 = DATA_DATASET.resolve_target(
        materialization='daily', partition={'year': '2026', 'month': '09', 'day': '25'}
    )
    day2 = DATA_DATASET.resolve_target(
        materialization='daily', partition={'year': '2026', 'month': '09', 'day': '26'}
    )
    first = runtime.tables[day1.identifier].to_pylist()[0]
    second = runtime.tables[day2.identifier].to_pylist()[0]
    assert first == {
        'timestamp': early,
        'mp10': 42.0,
        'vel': 2.0,
        'dir': None,
        'estacion_mp10': HM3,
    }
    assert second == {
        'timestamp': late,
        'mp10': 50.0,
        'vel': None,
        'dir': 190.0,
        'estacion_mp10': HM3,
    }
    assert all(num == 1 for operation, _, num in runtime.writes if operation == 'merge')


def test_daily_hm_fallback_upgrades_when_hm3_arrives_later():
    runtime = MemoryRuntime()
    materializer = MeteodataMaterializer(runtime=runtime)
    timestamp = datetime(2026, 9, 25, 23, 40, tzinfo=UTC)
    assert (
        materializer.publish_data(
            measurements=(Measurement(timestamp, HM, 'mp10', 41.0),), context=Context()
        )
        == 1
    )
    assert (
        materializer.publish_data(
            measurements=(Measurement(timestamp, HM3, 'mp10', 43.0),), context=Context()
        )
        == 1
    )
    assert (
        materializer.publish_data(
            measurements=(Measurement(timestamp, HM, 'mp10', 41.0),), context=Context()
        )
        == 0
    )
    target = DATA_DATASET.resolve_target(
        materialization='daily', partition={'year': '2026', 'month': '09', 'day': '25'}
    )
    assert runtime.tables[target.identifier].to_pylist()[0]['estacion_mp10'] == HM3
