from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from dash import dcc, html

from ada.web.ui.display_status import DisplayStatus, resolve_status_visual
from ada.web.ui.time_series import TimeSeriesPoint, TimeSeriesValues, build_time_series_component
from ada.web.ui.time_series.presentation import _santiago_labels


def _utc(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 4, 5, hour, minute, tzinfo=UTC)


def test_dst_fallback_repeated_local_time_is_distinguished_without_changing_utc():
    moments = [_utc(2, 30), _utc(3, 30)]
    labels = _santiago_labels(moments, moments)
    assert labels == ['23:30 UTC-03:00', '23:30 UTC-04:00']
    series = TimeSeriesValues(
        DisplayStatus.OK,
        (TimeSeriesPoint(moments[0], 1.5), TimeSeriesPoint(moments[1], 2.5)),
    )
    graph = build_time_series_component(series)
    assert isinstance(graph, dcc.Graph)
    figure = graph.figure
    assert list(figure.data[0].x) == [item.isoformat() for item in moments]
    assert figure.layout.xaxis.ticktext == tuple(labels)
    assert figure.layout.xaxis.range == tuple(item.isoformat() for item in moments)
    assert graph.config['staticPlot'] is True
    assert graph.config['displayModeBar'] is False
    assert figure.layout.xaxis.fixedrange is True


def test_gaps_remain_null_and_do_not_reorder_or_interpolate():
    start = datetime(2026, 1, 2, 12, tzinfo=UTC)
    points = tuple(
        TimeSeriesPoint(start + timedelta(minutes=2 * i), item)
        for i, item in enumerate((7.5, None, 9.5))
    )
    graph = build_time_series_component(TimeSeriesValues(DisplayStatus.OK, points))
    assert list(graph.figure.data[0].y) == [7.5, None, 9.5]
    assert graph.figure.data[0].connectgaps is False


@pytest.mark.parametrize('status', [DisplayStatus.INVALID, DisplayStatus.ERROR])
def test_invalid_or_error_series_displays_own_status_icon(status):
    result = build_time_series_component(TimeSeriesValues(status))
    assert isinstance(result, html.Div)
    assert isinstance(result.children, html.Img)
    assert result.children.alt == resolve_status_visual(status).alt


@pytest.mark.parametrize('status', [DisplayStatus.NOT_MAPPED, DisplayStatus.EMPTY])
def test_missing_or_empty_delivery_keeps_blank_graph_without_fabricated_timestamps(status):
    graph = build_time_series_component(TimeSeriesValues(status))
    assert isinstance(graph, dcc.Graph)
    assert list(graph.figure.data[0].x) == []
    assert list(graph.figure.data[0].y) == []
    assert graph.figure.layout.xaxis.range is None


def test_all_null_samples_keep_utc_window_without_line_or_imputation():
    moments = (_utc(2, 30), _utc(3, 30))
    series = TimeSeriesValues(
        DisplayStatus.OK, tuple(TimeSeriesPoint(moment, None) for moment in moments)
    )
    graph = build_time_series_component(series)
    assert isinstance(graph, dcc.Graph)
    assert list(graph.figure.data[0].y) == [None, None]
    assert graph.figure.layout.xaxis.range == tuple(moment.isoformat() for moment in moments)
    assert graph.figure.data[0].connectgaps is False


def test_numeric_values_are_passed_through_without_converting_integer_to_float():
    moments = (_utc(2, 30), _utc(3, 30))
    series = TimeSeriesValues(
        DisplayStatus.OK, (TimeSeriesPoint(moments[0], 17), TimeSeriesPoint(moments[1], 17.5))
    )
    graph = build_time_series_component(series)
    assert list(graph.figure.data[0].y) == [17, 17.5]
    assert type(graph.figure.data[0].y[0]) is int


def test_rejects_duplicate_or_non_utc_timestamps_and_nonfinite_values():
    moment = _utc(2)
    with pytest.raises(ValueError):
        TimeSeriesValues(DisplayStatus.OK, (TimeSeriesPoint(moment, 1), TimeSeriesPoint(moment, 2)))
    with pytest.raises(ValueError):
        TimeSeriesPoint(moment, float('nan'))
    with pytest.raises(ValueError):
        TimeSeriesPoint(moment.astimezone(__import__('zoneinfo').ZoneInfo('America/Santiago')), 1)
