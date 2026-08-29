# Presentación inicial no congelada: expone data-* estables para TS-003/TS-009 sin fijar todavía colores ni animaciones.
from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from .models import (
    TimeStatusSourceCondition,
    TimeStatusSourceState,
    TimeStatusSummaryState,
)


def build_time_status_summary(*, state: TimeStatusSummaryState) -> Component:
    sources = state.required_sources
    attributes = {
        'data-component-key': 'time_status',
        'data-has-dispatch': 'true' if state.dispatch is not None else 'false',
        'data-has-detail': 'true' if state.has_detail else 'false',
        'data-content-stale': 'true' if state.content_stale else 'false',
        'data-has-data-error': 'true' if state.data_error_source_keys else 'false',
    }
    if state.has_detail:
        attributes['data-ada-time-status-detail-trigger'] = 'true'

    return html.Div(
        className='ada-time-status',
        children=[
            html.Span(
                className='ada-time-status__sources',
                children=[
                    _build_source(source, divided=index < len(sources) - 1)
                    for index, source in enumerate(sources)
                ],
            ),
            _build_current_datetime(state.current_datetime),
        ],
        **attributes,
    )


def _build_source(source: TimeStatusSourceState, *, divided: bool) -> Component:
    source_class = 'ada-time-status__source'
    if divided:
        source_class += ' ada-time-status__source--divided'

    return html.Span(
        className=source_class,
        **{
            'data-source-key': source.key,
            'data-source-condition': source.condition.value,
            'data-source-timestamp-utc': source.timestamp_iso or '',
            'data-warning-after-seconds': str(source.policy.warning_after_seconds),
            'data-stale-after-seconds': str(source.policy.stale_after_seconds),
        },
        children=html.Span(
            className=(
                'ada-time-status__source-content '
                f'ada-time-status__source-content--{source.condition.value}'
            ),
            children=[
                html.I(className=f'{_icon_class(source.condition)} ada-time-status__item'),
                html.P(className='ada-time-status__item', children=source.label),
                html.P(className='ada-time-status__item', children='•'),
                html.P(
                    className='ada-time-status__timestamp ada-time-status__timestamp--source',
                    title=source.timestamp_iso or '',
                    children=source.relative_age_text or '--',
                ),
            ],
        ),
    )


def _build_current_datetime(current_datetime: str) -> Component:
    return html.Span(
        className='ada-time-status__current',
        children=html.Span(
            className='ada-time-status__current-content',
            children=[
                html.I(className='bi bi-clock ada-time-status__item'),
                html.P(
                    className='ada-time-status__item ada-time-status__current-label',
                    children='Fecha y hora',
                ),
                html.P(className='ada-time-status__item', children='•'),
                html.P(
                    className='ada-time-status__timestamp ada-time-status__timestamp--datetime',
                    title=current_datetime,
                    children=current_datetime,
                    **{'data-ada-time-status-clock': 'true'},
                ),
            ],
        ),
    )


def _icon_class(condition: TimeStatusSourceCondition) -> str:
    if condition is TimeStatusSourceCondition.HARD_STALE:
        return 'bi bi-cloud-slash'
    if condition is TimeStatusSourceCondition.DATA_ERROR:
        return 'bi bi-exclamation-triangle'
    return 'bi bi-cloud-check'
