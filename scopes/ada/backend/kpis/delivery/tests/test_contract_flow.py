from datetime import UTC, datetime, timedelta

from ada.kpis.delivery import (
    KpiDeliveryBinding,
    KpiDeliveryConfiguration,
    KpiDeliveryStatus,
    KpiLatestValue,
    project_kpi_latest,
    project_kpi_timeseries,
)


def test_configuration_drives_latest_and_series_independently() -> None:
    configuration = KpiDeliveryConfiguration(
        revision='cfg-7',
        tool_projection_revision='tools-3',
        bindings=(
            KpiDeliveryBinding(
                key='production',
                destination_keys=('global_indicators', 'milling'),
                latest_enabled=True,
                series_enabled=True,
                series_hours=1,
            ),
            KpiDeliveryBinding(
                key='disabled',
                destination_keys=('milling',),
                latest_enabled=False,
                series_enabled=False,
            ),
        ),
    )
    end = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    latest = project_kpi_latest(
        configuration=configuration,
        values={'production': KpiLatestValue(KpiDeliveryStatus.OK, 'value', 66)},
        watermark_utc=end,
        published_at_utc=end,
    )
    series = project_kpi_timeseries(
        configuration=configuration,
        histories={'production': {end: 66, end - timedelta(minutes=2): 65}},
        historian_revision='hist-9',
        end_utc=end,
        published_at_utc=end,
    )
    assert set(latest.destinations) == {'global_indicators', 'milling'}
    assert set(series.destinations) == {'global_indicators', 'milling'}
    assert 'disabled' not in latest.destinations['milling']
    assert 'disabled' not in series.destinations['milling']
    assert (
        latest.manifest.configuration_revision == series.manifest.configuration_revision == 'cfg-7'
    )
