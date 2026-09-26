from datetime import UTC, datetime

from atlanticus.data_producers.meteodata.consolidation import consolidate
from atlanticus.data_producers.meteodata.models import HM, HM3, Measurement

T = datetime(2026, 9, 26, 1, tzinfo=UTC)


def measure(station, variable, value):
    return Measurement(timestamp=T, station=station, variable=variable, value=value)


def test_hm3_priority_is_independent_of_arrival_order():
    for samples in (
        (measure(HM, 'mp10', 40), measure(HM3, 'mp10', 42)),
        (measure(HM3, 'mp10', 42), measure(HM, 'mp10', 40)),
    ):
        result = consolidate(existing={}, measurements=samples)
        assert result[T]['mp10'] == 42
        assert result[T]['estacion_mp10'] == HM3


def test_delayed_hm_does_not_downgrade_existing_hm3_and_completes_vel_dir():
    previous = {T: {'timestamp': T, 'mp10': 42.0, 'vel': None, 'dir': None, 'estacion_mp10': HM3}}
    result = consolidate(
        existing=previous,
        measurements=(measure(HM, 'mp10', 40), measure(HM, 'vel', 2.2), measure(HM, 'dir', 190)),
    )
    assert result == {T: {'timestamp': T, 'mp10': 42.0, 'vel': 2.2, 'dir': 190.0, 'estacion_mp10': HM3}}


def test_delayed_hm3_upgrades_previous_hm_fallback():
    previous = {T: {'timestamp': T, 'mp10': 40.0, 'vel': 2.2, 'dir': None, 'estacion_mp10': HM}}
    result = consolidate(existing=previous, measurements=(measure(HM3, 'mp10', 42),))
    assert result[T] == {'timestamp': T, 'mp10': 42.0, 'vel': 2.2, 'dir': None, 'estacion_mp10': HM3}


def test_existing_values_are_preserved_when_a_query_returns_only_one_variable():
    previous = {T: {'timestamp': T, 'mp10': 42.0, 'vel': 2.2, 'dir': 190.0, 'estacion_mp10': HM3}}
    assert consolidate(existing=previous, measurements=(measure(HM, 'mp10', 40),)) == {}
    result = consolidate(existing=previous, measurements=(measure(HM, 'vel', 2.3),))
    assert result[T]['vel'] == 2.3
    assert result[T]['dir'] == 190.0
    assert result[T]['mp10'] == 42.0


def test_station_measurements_are_not_force_aligned_to_other_timestamps():
    earlier = datetime(2026, 9, 26, 0, 50, tzinfo=UTC)
    result = consolidate(
        existing={},
        measurements=(
            Measurement(timestamp=earlier, station=HM, variable='vel', value=2.2),
            Measurement(timestamp=T, station=HM3, variable='mp10', value=42),
        ),
    )
    assert result[earlier]['mp10'] is None
    assert result[T]['vel'] is None
