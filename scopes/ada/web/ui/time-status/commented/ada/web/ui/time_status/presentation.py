# TS-012B afina la lectura visual: PI/Dispatch son el trigger y el popover comunica únicamente fuentes adicionales.
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
    # tool_key sigue siendo la identidad usada para restaurar una Surface abierta tras un rerender de Dash.
    normalized_tool_key = tool_key.strip()
    if not normalized_tool_key:
        raise TimeStatusDefinitionError('Time Status tool_key must not be empty')
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
    source_attributes = {}
    if state.has_detail:
        # Sólo PI/Dispatch exponen interacción; el reloj queda visual y semánticamente fuera de este botón.
        source_attributes.update(
            {
                'data-ada-time-status-detail-trigger': 'true',
                'role': 'button',
                'tabIndex': 0,
                'aria-expanded': 'false',
                'aria-label': 'Ver fuentes de datos adicionales',
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
                **source_attributes,
            ),
            _build_current_datetime(state.current_datetime),
        ],
        **{
            'data-component-key': 'time_status',
            'data-has-dispatch': 'true' if state.dispatch is not None else 'false',
            'data-has-detail': 'true' if state.has_detail else 'false',
            'data-content-stale': 'true' if state.content_stale else 'false',
            'data-has-data-error': 'true' if state.data_error_source_keys else 'false',
        },
    )


def build_time_status_detail(*, state: TimeStatusDetailState) -> Component:
    # Las filas aquí son exclusivamente fuentes adicionales y siempre son informativas para la salud global.
    return html.Div(
        className='ada-time-status-detail__content',
        children=[
            _build_detail_heading(),
            *[_build_detail_source(source) for source in state.sources],
        ],
        **{'data-ada-time-status-detail-content': 'true'},
    )


def _build_detail_surface(detail: Component | None) -> Component:
    # detail=None no deja un panel vacío: representa explícitamente que la Tool no consume fuentes adicionales.
    return html.Div(
        className='ada-time-status-detail',
        hidden=True,
        children=detail if detail is not None else _build_empty_detail(),
        **{
            'data-ada-time-status-detail-surface': 'true',
            'data-ada-time-status-detail-placement': 'bottom',
            'aria-hidden': 'true',
        },
    )


def _build_detail_heading() -> Component:
    return html.P(
        className='ada-time-status-detail__heading',
        children='Fuentes adicionales',
    )


def _build_empty_detail() -> Component:
    return html.Div(
        className='ada-time-status-detail__content',
        children=[
            _build_detail_heading(),
            html.Div(
                className='ada-time-status-detail__empty',
                children=[
                    html.P(
                        className='ada-time-status-detail__empty-title',
                        children='Sin fuentes adicionales',
                    ),
                    html.P(
                        className='ada-time-status-detail__empty-copy',
                        children='Esta herramienta no consume fuentes de datos adicionales.',
                    ),
                ],
                **{'data-ada-time-status-detail-empty': 'true'},
            ),
        ],
        **{'data-ada-time-status-detail-content': 'true'},
    )


def _build_detail_source(source: TimeStatusDetailSourceState) -> Component:
    # El rol es fijo: cualquier fuente del Detail es adicional e informativa.
    return html.Div(
        className='ada-time-status-detail__source',
        children=[
            html.Span(className='ada-time-status-detail__source-label', children=source.label),
            html.Span(
                className='ada-time-status-detail__source-value',
                children=source.value,
            ),
        ],
        **{
            'data-ada-time-status-detail-source': 'true',
            'data-source-key': source.key,
            'data-source-role': 'informational',
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
                _build_source_value(source),
            ],
        ),
    )


def _build_source_value(source: TimeStatusSourceState) -> Component:
    class_name = 'ada-time-status__timestamp ada-time-status__timestamp--source'
    if source.condition is TimeStatusSourceCondition.DATA_ERROR:
        # La nube sigue identificando la fuente; el triángulo ocupa la posición del valor temporal inválido.
        return html.I(
            className=f'bi bi-exclamation-triangle {class_name} ada-time-status__timestamp--error',
            role='img',
            **{
                'data-ada-time-status-source-value': 'true',
                'aria-label': 'Error de información temporal',
            },
        )
    return html.P(
        className=class_name,
        children=source.relative_age_text,
        **{'data-ada-time-status-source-value': 'true'},
    )


def _build_current_datetime(current_datetime: str) -> Component:
    # Fecha y hora se presenta como una unidad compacta al extremo derecho y no usa tooltip nativo.
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
                    children=current_datetime,
                    **{'data-ada-time-status-clock': 'true'},
                ),
            ],
        ),
    )


def _icon_class(condition: TimeStatusSourceCondition) -> str:
    # Tanto hard stale como data error mantienen el ícono de nube caída; el error temporal se marca en el valor.
    if condition in {
        TimeStatusSourceCondition.HARD_STALE,
        TimeStatusSourceCondition.DATA_ERROR,
    }:
        return 'bi bi-cloud-slash'
    return 'bi bi-cloud-check'
