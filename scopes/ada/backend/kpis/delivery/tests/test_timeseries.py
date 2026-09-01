from datetime import UTC, datetime, timedelta

import pytest

from ada.kpis.delivery import (
    TIMESERIES_STEP_SECONDS,
    KpiDeliveryBinding,
    KpiDeliveryConfiguration,
    KpiDeliveryValidationError,
    KpiTimeseriesHistory,
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


def _history(value_type: str, values: dict[datetime, str]) -> KpiTimeseriesHistory:
    return KpiTimeseriesHistory(value_type=value_type, values=values)


def test_timeseries_end_uses_absolute_120_second_grid() -> None:
    assert align_timeseries_end(datetime(2026, 9, 1, 10, 5, 47, tzinfo=UTC)) == datetime(
        2026, 9, 1, 10, 4, tzinfo=UTC
    )
    assert TIMESERIES_STEP_SECONDS == 120


def test_float_series_reconstructs_native_values_only_from_declared_type() -> None:
    end = datetime(2026, 9, 1, 10, 4, tzinfo=UTC)
    start = end - timedelta(hours=1)
    snapshot = project_kpi_timeseries(
        configuration=_configuration(),
        histories={
            'production': _history(
                'float',
                {
                    start + timedelta(minutes=2): '4.29',
                    end: '4.30',
                },
            )
        },
        historian_revision='hist-1',
        end_utc=end,
        published_at_utc=end,
    )
    series = snapshot.series['production']
    assert snapshot.manifest.schema_version == 2
    assert series.value_type == 'float'
    assert series.values[0] == 4.29
    assert series.values[-1] == 4.3


def test_text_one_stays_text_and_is_not_inferred_as_integer_or_boolean() -> None:
    end = datetime(2026, 9, 1, 10, 4, tzinfo=UTC)
    start = end - timedelta(hours=3)
    snapshot = project_kpi_timeseries(
        configuration=_configuration(),
        histories={
            'state': _history(
                'text',
                {
                    start + timedelta(minutes=2): '1',
                    start + timedelta(minutes=6): '0',
                },
            )
        },
        historian_revision='hist-1',
        end_utc=end,
        published_at_utc=end,
    )
    values = snapshot.series['state'].values
    assert snapshot.series['state'].value_type == 'text'
    assert values[0] == '1'
    assert values[1] is None
    assert values[2] == '0'


def test_integer_and_boolean_series_use_explicit_type_contract() -> None:
    end = datetime(2026, 9, 1, 10, 4, tzinfo=UTC)
    start = end - timedelta(hours=1)
    integer = project_kpi_timeseries(
        configuration=_configuration(),
        histories={'production': _history('integer', {start + timedelta(minutes=2): '1'})},
        historian_revision='hist-1',
        end_utc=end,
        published_at_utc=end,
    )
    boolean = project_kpi_timeseries(
        configuration=_configuration(),
        histories={'production': _history('boolean', {start + timedelta(minutes=2): 'true'})},
        historian_revision='hist-1',
        end_utc=end,
        published_at_utc=end,
    )
    assert integer.series['production'].values[0] == 1
    assert type(integer.series['production'].values[0]) is int
    assert boolean.series['production'].values[0] is True


def test_boolean_does_not_accept_numeric_conventions() -> None:
    end = datetime(2026, 9, 1, 10, 4, tzinfo=UTC)
    start = end - timedelta(hours=1)
    with pytest.raises(KpiDeliveryValidationError, match='boolean'):
        project_kpi_timeseries(
            configuration=_configuration(),
            histories={'production': _history('boolean', {start + timedelta(minutes=2): '1'})},
            historian_revision='hist-1',
            end_utc=end,
            published_at_utc=end,
        )


def test_missing_exact_point_is_null_without_nearest_or_fill() -> None:
    end = datetime(2026, 9, 1, 10, 4, tzinfo=UTC)
    start = end - timedelta(hours=1)
    snapshot = project_kpi_timeseries(
        configuration=_configuration(),
        histories={
            'production': _history(
                'float',
                {
                    start + timedelta(minutes=1, seconds=59): '11.0',
                    start + timedelta(minutes=4): '22.0',
                },
            )
        },
        historian_revision='hist-1',
        end_utc=end,
        published_at_utc=end,
    )
    values = snapshot.series['production'].values
    assert values[0] is None
    assert values[1] == 22.0
    assert values[2] is None


def test_empty_history_keeps_null_series_without_inventing_type() -> None:
    end = datetime(2026, 9, 1, 10, 4, tzinfo=UTC)
    snapshot = project_kpi_timeseries(
        configuration=_configuration(hours=24),
        histories={},
        historian_revision='hist-1',
        end_utc=end,
        published_at_utc=end,
    )
    series = snapshot.series['production']
    assert len(series.values) == 720
    assert series.value_type is None
    assert all(value is None for value in series.values)


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
