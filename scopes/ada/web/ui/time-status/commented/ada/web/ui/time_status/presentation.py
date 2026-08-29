# TS-008 agrega contenido dinámico al Detail sin otorgar autoridad operacional a fuentes informativas.
from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from .errors import TimeStatusDefinitionError
from .models import (
    TimeStatusDetailSourceState,
    TimeStatusDetailState,
    TimeStatusSourceCondition,
    TimeStatusSourceState,
    TimeStatusSummaryState,
)


def build_time_status(
    *,
    tool_key: str,
    state: TimeStatusSummaryState,
    detail: Component | None = None,
) -> Component:
    # tool_key sigue siendo la identidad estable de la instancia para TS-007 y no cambia con TS-008.
    normalized_tool_key = tool_key.strip()
    if not normalized_tool_key:
        raise TimeStatusDefinitionError('Time Status tool_key must not be empty')

    # No permitimos contenido Detail inaccesible si el Summary no declara la interacción.
    if detail is not None and not state.has_detail:
        raise TimeStatusDefinitionError('Time Status detail content requires has_detail=True')

    children = [build_time_status_summary(state=state)]
    if state.has_detail:
        children.append(_build_detail_surface(detail))

    attributes = {
        'data-ada-time-status-container': 'true',
        'data-ada-time-status-tool-key': normalized_tool_key,
    }
    if state.has_detail:
        attributes['data-ada-time-status-detail-open'] = 'false'

    return html.Div(
        className='ada-time-status-container',
        children=children,
        **attributes,
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
        attributes.update(
            {
                'data-ada-time-status-detail-trigger': 'true',
                'role': 'button',
                'tabIndex': 0,
                'aria-expanded': 'false',
            }
        )

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


def build_time_status_detail(*, state: TimeStatusDetailState) -> Component:
    # Sólo se renderizan las filas recibidas en el contrato de consumo; no se descubren fuentes globales ni se agregan faltantes.
    return html.Div(
        className='ada-time-status-detail__content',
        children=[_build_detail_source(source) for source in state.sources],
        **{'data-ada-time-status-detail-content': 'true'},
    )


def _build_detail_surface(detail: Component | None) -> Component:
    return html.Div(
        className='ada-time-status-detail',
        hidden=True,
        children=detail,
        **{
            'data-ada-time-status-detail-surface': 'true',
            'aria-hidden': 'true',
        },
    )


def _build_detail_source(source: TimeStatusDetailSourceState) -> Component:
    # El rol se deriva del modelo. En TS-008 es sólo metadata semántica y no agrega colores, stale ni parpadeo.
    role = 'control' if source.is_control else 'informational'
    return html.Div(
        className='ada-time-status-detail__source',
        children=[
            html.Span(className='ada-time-status-detail__source-label', children=source.label),
            html.Span(
                className='ada-time-status-detail__source-value',
                title=source.value,
                children=source.value,
            ),
        ],
        **{
            'data-ada-time-status-detail-source': 'true',
            'data-source-key': source.key,
            'data-source-role': role,
        },
    )


def _build_source(source: TimeStatusSourceState, *, divided: bool) -> Component:
    source_class = 'ada-time-status__source'
    if divided:
        source_class += ' ada-time-status__source--divided'

    return html.Span(
        className=source_class,
        **{
            'data-ada-time-status-source': 'true',
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
            **{'data-ada-time-status-source-content': 'true'},
            children=[
                html.I(
                    className=f'{_icon_class(source.condition)} ada-time-status__item',
                    **{'data-ada-time-status-source-icon': 'true'},
                ),
                html.P(className='ada-time-status__item', children=source.label),
                html.P(className='ada-time-status__item', children='•'),
                html.P(
                    className='ada-time-status__timestamp ada-time-status__timestamp--source',
                    title=source.timestamp_iso or '',
                    children=source.relative_age_text or '--',
                    **{'data-ada-time-status-source-value': 'true'},
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
