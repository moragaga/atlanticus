from datetime import UTC, datetime

import pytest

from atlanticus.connectivity.http import HttpConnectionError
from atlanticus.data_producers.meteodata.acquisition import MeteodataAcquirer
from atlanticus.data_producers.meteodata.errors import MeteodataAcquisitionError, MeteodataResponseError
from atlanticus.data_producers.meteodata.models import HM, HM3


class FakeClient:
    def __init__(self, *, replies=None, errors=(), projection_ts_last=1790364600000):
        self.calls = []
        self.replies = replies or {}
        self.errors = set(errors)
        self.projection_ts_last = projection_ts_last

    def request_json(self, method, endpoint, **kwargs):
        assert method == 'GET'
        assert endpoint == 'consultas'
        params = kwargs['params']
        self.calls.append(params)
        key = params.get('est'), params.get('var')
        if key in self.errors:
            raise HttpConnectionError('private endpoint unavailable')
        if params['op'] == 'proyeccion':
            return {
                'promedio_dia': 36.9,
                'proyeccion': 37.9,
                'ts_last': self.projection_ts_last,
                'monitoreo_oficial': True,
            }
        return self.replies.get(
            key,
            {'estacion': key[0], 'variable': key[1], 'datos': []},
        )


@pytest.mark.parametrize(
    ('source_wall_clock', 'expected_utc'),
    (
        (datetime(2026, 9, 25, 19, 30), datetime(2026, 9, 25, 23, 30, tzinfo=UTC)),
        (datetime(2026, 9, 25, 23, 50), datetime(2026, 9, 26, 3, 50, tzinfo=UTC)),
        (datetime(2026, 1, 15, 19, 30), datetime(2026, 1, 15, 23, 30, tzinfo=UTC)),
    ),
)
def test_projection_always_decodes_fixed_gmt_minus_four_wall_clock(
    source_wall_clock, expected_utc
):
    encoded_milliseconds = int(source_wall_clock.replace(tzinfo=UTC).timestamp() * 1000)
    acquirer = MeteodataAcquirer(client=FakeClient(projection_ts_last=encoded_milliseconds))
    projection = acquirer.acquire_projection()
    assert projection.timestamp == expected_utc
    assert projection.proyeccion_mp10 == 37.9
    assert projection.promedio_dia_mp10 == 36.9
    assert projection.monitoreo_oficial is True


def test_four_queries_use_fixed_gmt_minus_four_even_during_chilean_dst():
    responses = {
        (HM3, 'mp10'): {
            'estacion': HM3,
            'variable': 'mp10',
            'datos': [['2026-09-25 19:40:00', 70.0]],
        },
    }
    client = FakeClient(replies=responses)
    acquirer = MeteodataAcquirer(client=client)
    batch = acquirer.acquire_data(now_utc=datetime(2026, 9, 25, 23, 46, tzinfo=UTC), lookback_minutes=90)
    assert [(m.station, m.variable, m.timestamp, m.value) for m in batch.measurements] == [
        (HM3, 'mp10', datetime(2026, 9, 25, 23, 40, tzinfo=UTC), 70.0)
    ]
    assert batch.successful_queries == 4
    assert len(client.calls) == 4
    assert {(c['est'], c['var']) for c in client.calls} == {
        (HM, 'mp10'), (HM3, 'mp10'), (HM, 'vel'), (HM, 'dir')
    }
    assert {c['tini'] for c in client.calls} == {'20260925_181600'}
    assert {c['tfin'] for c in client.calls} == {'20260925_194600'}


def test_partial_failure_does_not_discard_other_station_data():
    responses = {
        (HM, 'mp10'): {
            'estacion': HM, 'variable': 'mp10', 'datos': [['2026-09-25 19:30:00', 44.0]],
        },
    }
    client = FakeClient(replies=responses, errors={(HM3, 'mp10')})
    batch = MeteodataAcquirer(client=client).acquire_data(
        now_utc=datetime(2026, 9, 25, 23, 46, tzinfo=UTC), lookback_minutes=90
    )
    assert batch.successful_queries == 3
    assert batch.failed_queries == (f'{HM3}.mp10',)
    assert [(m.station, m.value) for m in batch.measurements] == [(HM, 44.0)]


def test_every_query_failing_is_not_confused_with_no_updates():
    client = FakeClient(errors={(HM, 'mp10'), (HM3, 'mp10'), (HM, 'vel'), (HM, 'dir')})
    with pytest.raises(MeteodataAcquisitionError, match='all Meteodata'):
        MeteodataAcquirer(client=client).acquire_data(
            now_utc=datetime(2026, 9, 25, 23, 46, tzinfo=UTC), lookback_minutes=90
        )


def test_mismatched_response_is_not_used_as_a_different_source():
    client = FakeClient(
        replies={(HM3, 'mp10'): {'estacion': HM, 'variable': 'mp10', 'datos': [["2026-09-25 19:30:00", 30.0]]}}
    )
    batch = MeteodataAcquirer(client=client).acquire_data(
        now_utc=datetime(2026, 9, 25, 23, 46, tzinfo=UTC), lookback_minutes=90
    )
    assert batch.failed_queries == (f'{HM3}.mp10',)
    assert batch.successful_queries == 3


def test_invalid_projection_rejected_without_publishing():
    class BadClient:
        def request_json(self, method, endpoint, **kwargs):
            return {'ts_last': True, 'promedio_dia': 2, 'proyeccion': 3, 'monitoreo_oficial': True}

    with pytest.raises(MeteodataResponseError):
        MeteodataAcquirer(client=BadClient()).acquire_projection()
