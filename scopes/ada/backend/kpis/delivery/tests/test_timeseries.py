from datetime import UTC, datetime, timedelta

from ada.kpis.delivery import (
    TIMESERIES_STEP_SECONDS,
    KpiDeliveryBinding,
    KpiDeliveryConfiguration,
    align_timeseries_end,
    project_kpi_timeseries,
)


def _configuration(*, hours: int = 1) -> KpiDeliveryConfiguration:
    return KpiDeliveryConfiguration(
        revision='cfg-1',
        tool_projection_revision='tool-1',
        bindings=(
            KpiDeliveryBinding(
                key='production',
                destination_keys=('global_indicators', 'milling'),
                latest_enabled=True,
                series_enabled=True,
                series_hours=hours,
            ),
            KpiDeliveryBinding(
                key='state',
                destination_keys=('global_indicators',),
                latest_enabled=False,
                series_enabled=True,
                series_hours=3,
            ),
        ),
    )


def test_timeseries_end_uses_absolute_120_second_grid() -> None:
    assert align_timeseries_end(datetime(2026, 9, 1, 10, 5, 47, tzinfo=UTC)) == datetime(
        2026, 9, 1, 10, 4, tzinfo=UTC
    )
    assert TIMESERIES_STEP_SECONDS == 120


def test_one_hour_has_30_positions_and_window_is_open_left_closed_right() -> None:
    end = datetime(2026, 9, 1, 10, 4, tzinfo=UTC)
    start = end - timedelta(hours=1)
    history = {
        start: 999,
        start + timedelta(minutes=2): 10,
        end: 20,
    }
    snapshot = project_kpi_timeseries(
        configuration=_configuration(),
        histories={'production': history},
        historian_revision='hist-1',
        end_utc=end,
        published_at_utc=end,
    )
    series = snapshot.series['production']
    assert len(series.values) == 30
    assert series.values[0] == 10
    assert series.values[-1] == 20
    assert 999 not in series.values


def test_24_hours_has_720_positions() -> None:
    end = datetime(2026, 9, 1, 10, 4, tzinfo=UTC)
    snapshot = project_kpi_timeseries(
        configuration=_configuration(hours=24),
        histories={},
        historian_revision='hist-1',
        end_utc=end,
        published_at_utc=end,
    )
    assert len(snapshot.series['production'].values) == 720


def test_missing_exact_point_is_null_without_nearest_or_fill() -> None:
    end = datetime(2026, 9, 1, 10, 4, tzinfo=UTC)
    start = end - timedelta(hours=1)
    history = {
        start + timedelta(minutes=1, seconds=59): 11,
        start + timedelta(minutes=4): 22,
    }
    snapshot = project_kpi_timeseries(
        configuration=_configuration(),
        histories={'production': history},
        historian_revision='hist-1',
        end_utc=end,
        published_at_utc=end,
    )
    values = snapshot.series['production'].values
    assert values[0] is None
    assert values[1] == 22
    assert values[2] is None


def test_series_can_transport_text_and_missing_values() -> None:
    end = datetime(2026, 9, 1, 10, 4, tzinfo=UTC)
    start = end - timedelta(hours=3)
    snapshot = project_kpi_timeseries(
        configuration=_configuration(),
        histories={
            'state': {
                start + timedelta(minutes=2): 'RUN',
                start + timedelta(minutes=6): 'STOP',
            }
        },
        historian_revision='hist-1',
        end_utc=end,
        published_at_utc=end,
    )
    values = snapshot.series['state'].values
    assert values[0] == 'RUN'
    assert values[1] is None
    assert values[2] == 'STOP'


def test_series_is_not_duplicated_for_multiple_destinations() -> None:
    end = datetime(2026, 9, 1, 10, 4, tzinfo=UTC)
    snapshot = project_kpi_timeseries(
        configuration=_configuration(),
        histories={},
        historian_revision='hist-1',
        end_utc=end,
        published_at_utc=end,
    )
    assert tuple(snapshot.series) == ('production', 'state')
    assert snapshot.destinations['global_indicators'] == ('production', 'state')
    assert snapshot.destinations['milling'] == ('production',)


def test_timeseries_revision_ignores_published_at_but_uses_historian_revision() -> None:
    end = datetime(2026, 9, 1, 10, 5, 47, tzinfo=UTC)
    first = project_kpi_timeseries(
        configuration=_configuration(),
        histories={},
        historian_revision='hist-1',
        end_utc=end,
        published_at_utc=end,
    )
    second = project_kpi_timeseries(
        configuration=_configuration(),
        histories={},
        historian_revision='hist-1',
        end_utc=end,
        published_at_utc=end + timedelta(minutes=5),
    )
    corrected = project_kpi_timeseries(
        configuration=_configuration(),
        histories={},
        historian_revision='hist-2',
        end_utc=end,
        published_at_utc=end + timedelta(minutes=5),
    )
    assert first.manifest.revision == second.manifest.revision
    assert first.manifest.revision != corrected.manifest.revision


def test_end_changes_inside_same_grid_cell_do_not_change_revision() -> None:
    first_end = datetime(2026, 9, 1, 10, 4, 10, tzinfo=UTC)
    second_end = datetime(2026, 9, 1, 10, 5, 59, tzinfo=UTC)
    first = project_kpi_timeseries(
        configuration=_configuration(),
        histories={},
        historian_revision='hist-1',
        end_utc=first_end,
        published_at_utc=first_end,
    )
    second = project_kpi_timeseries(
        configuration=_configuration(),
        histories={},
        historian_revision='hist-1',
        end_utc=second_end,
        published_at_utc=second_end,
    )
    assert first.end_utc == second.end_utc == '2026-09-01T10:04:00Z'
    assert first.manifest.revision == second.manifest.revision
