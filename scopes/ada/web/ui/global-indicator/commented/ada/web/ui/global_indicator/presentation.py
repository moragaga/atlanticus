# Presentación reusable: sólo el nodo que representa un valor recibe el atributo de Inspection.
from __future__ import annotations

import re

from dash import html
from dash.development.base_component import Component

from ada.web.ui.display_status import (
    DisplayStatus,
    DisplayValue,
    build_display_status_icon,
)

from .models import (
    GlobalIndicatorCollection,
    GlobalIndicatorLastMeasurementState,
    GlobalIndicatorMeasurementState,
    GlobalIndicatorState,
    GlobalIndicatorStyle,
    IndicatorColorClass,
)

_CLASS_TOKEN = re.compile(r'^[A-Za-z_][A-Za-z0-9_-]*$')


def build_global_indicators(*, collection: GlobalIndicatorCollection) -> Component:
    return html.Div(
        className='global-indicators',
        children=[build_global_indicator(state=indicator) for indicator in collection.indicators],
    )


def build_global_indicator(*, state: GlobalIndicatorState) -> Component:
    # El root/heading siguen neutrales para evitar que todo el slot parezca seleccionable.
    return html.Div(
        className='global-indicator',
        **{
            'data-indicator-key': state.key,
            'data-measurement-count': str(len(state.measurements)),
            'data-has-last-measurement': 'true' if state.last_measurement is not None else 'false',
        },
        children=[
            _build_label(
                label=state.label,
                unit=state.unit,
                class_name=state.style.heading_class,
            ),
            html.Div(
                className='global-indicator__content',
                children=_build_indicator_content(
                    measurements=state.measurements,
                    last_measurement=state.last_measurement,
                    style=state.style,
                ),
            ),
        ],
    )


def _build_label(*, label: str, unit: str, class_name: str) -> Component:
    return html.Div(
        className=f'global-indicator__heading {class_name}',
        children=[
            html.P(
                className='global-indicator__label',
                title=label,
                children=[label],
            ),
            html.I(className='global-indicator__icon bi bi-arrow-right-short px-1'),
            html.P(className='global-indicator__unit', children=[unit]),
        ],
    )


def _build_indicator_content(
    *,
    measurements: tuple[GlobalIndicatorMeasurementState, ...],
    last_measurement: GlobalIndicatorLastMeasurementState | None,
    style: GlobalIndicatorStyle,
) -> tuple[Component, ...]:
    children: list[Component] = [
        _build_table(
            rows=[_build_table_row(state=measurement, style=style) for measurement in measurements]
        )
    ]
    if last_measurement is not None:
        children.append(
            _build_last_measurement_slot(
                state=last_measurement,
                style=style,
            )
        )
    return tuple(children)


def _build_table(*, rows: list[Component]) -> Component:
    return html.Table(
        className='global-indicator__table',
        children=[html.Tbody(children=rows)],
    )


def _build_table_row(
    *,
    state: GlobalIndicatorMeasurementState,
    style: GlobalIndicatorStyle,
) -> Component:
    return html.Tr(
        className='global-indicator__row',
        **{'data-measurement-key': state.key},
        children=[
            _build_table_value_cell(
                value=DisplayValue.ok(state.label),
                value_class_name=(
                    f'global-indicator__value--measurement-label {style.measurement_label_class}'
                ),
                is_header=True,
            ),
            _build_table_value_cell(
                value=state.actual_value,
                color_class=state.color_class,
                value_class_name=f'global-indicator__value--actual {style.actual_value_class}',
                # Actual puede apuntar a una Definition distinta del plan de la misma fila.
                inspection_key=state.actual_kpi_key,
            ),
            _build_table_separator_cell(class_name=style.plan_value_class),
            _build_table_value_cell(
                value=state.plan_value,
                value_class_name=f'global-indicator__value--plan {style.plan_value_class}',
                # Plan participa sólo cuando la composición declara explícitamente su propia identidad.
                inspection_key=state.plan_kpi_key,
            ),
        ],
    )


def _build_table_value_cell(
    *,
    value: DisplayValue | None,
    color_class: IndicatorColorClass = None,
    value_class_name: str = '',
    is_header: bool = False,
    inspection_key: str | None = None,
) -> Component:
    component = html.Th if is_header else html.Td
    attributes = {'scope': 'row'} if is_header else {}
    resolved_value = value or DisplayValue.empty()
    return component(
        className='global-indicator__cell',
        children=[
            html.P(
                className=' '.join(
                    part
                    for part in (
                        'global-indicator__value',
                        value_class_name,
                        _safe_class_names(value=color_class)
                        if resolved_value.status is DisplayStatus.OK
                        else '',
                    )
                    if part
                ),
                children=[_build_display_value(resolved_value)],
                **_inspection_attributes(inspection_key),
            )
        ],
        **attributes,
    )


def _build_table_separator_cell(*, class_name: str) -> Component:
    return html.Td(
        className='global-indicator__cell',
        children=[
            html.P(
                className=f'global-indicator__separator {class_name}',
                children=['/'],
            )
        ],
    )


def _build_last_measurement_slot(
    *,
    state: GlobalIndicatorLastMeasurementState,
    style: GlobalIndicatorStyle,
) -> Component:
    return html.Div(
        className='global-indicator__last-measurement',
        **{'data-measurement-key': state.key},
        children=[
            html.P(
                className=(
                    f'global-indicator__last-measurement-label {style.last_measurement_label_class}'
                ),
                children=[state.label],
            ),
            html.P(
                className=' '.join(
                    part
                    for part in (
                        'global-indicator__last-measurement-value',
                        style.last_measurement_value_class,
                        _safe_class_names(value=state.color_class)
                        if state.actual_value.status is DisplayStatus.OK
                        else '',
                    )
                    if part
                ),
                children=[_build_display_value(state.actual_value)],
                **_inspection_attributes(state.actual_kpi_key),
            ),
        ],
    )


def _inspection_attributes(kpi_key: str | None) -> dict[str, str | int]:
    # La frontera con Inspection continúa siendo sólo un atributo DOM opt-in.
    if kpi_key is None:
        return {}
    return {
        'data-kpi-inspection-key': kpi_key,
        'role': 'button',
        'tabIndex': 0,
        'aria-haspopup': 'dialog',
    }


def _build_display_value(value: DisplayValue) -> str | Component:
    if value.status is DisplayStatus.OK:
        if isinstance(value.value, Component):
            return value.value
        return str(value.value)

    icon = build_display_status_icon(
        value.status,
        class_name='global-indicator__status-icon',
    )
    if icon is not None:
        return icon
    return '-'


def _safe_class_names(*, value: IndicatorColorClass) -> str:
    if not isinstance(value, str):
        return ''
    tokens = value.split()
    if tokens and all(_CLASS_TOKEN.fullmatch(token) for token in tokens):
        return ' '.join(tokens)
    return ''
