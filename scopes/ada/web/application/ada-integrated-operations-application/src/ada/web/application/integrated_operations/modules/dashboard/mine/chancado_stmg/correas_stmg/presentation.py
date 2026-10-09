from __future__ import annotations

from collections.abc import Sequence

from dash import html
from dash.development.base_component import Component

from ada.web.application.integrated_operations.modules.dashboard.value_status import (
    DashboardValueStatus,
)
from ada.web.ui.display_status import DisplayStatus, DisplayValue, build_display_status_icon
from ada.web.ui.equipment_image import (
    EquipmentStateImage,
    LabelPosition,
    build_equipment_state_image,
)
from ada.web.ui.inline_row import (
    InlineValueRowDefinition,
    InlineValueRowState,
    InlineValueRowTone,
    build_inline_value_row,
)

from .definitions import CorreaStmgDefinition, CorreaStmgMetricDefinition
from .models import CorreasStmgState

_TONES = {
    DashboardValueStatus.NEUTRAL: InlineValueRowTone.DEFAULT,
    DashboardValueStatus.DANGER: InlineValueRowTone.DANGER,
    DashboardValueStatus.WARNING: InlineValueRowTone.WARNING,
}


def build_correas_stmg(
    definitions: Sequence[CorreaStmgDefinition],
    metric: CorreaStmgMetricDefinition,
    state: CorreasStmgState,
) -> Component:
    if not isinstance(definitions, Sequence) or len(definitions) != 3 or not all(
        isinstance(item, CorreaStmgDefinition) for item in definitions
    ):
        raise ValueError('Correa STMG requires exactly three definitions')
    if not isinstance(metric, CorreaStmgMetricDefinition):
        raise TypeError('metric must be CorreaStmgMetricDefinition')
    if not isinstance(state, CorreasStmgState) or len(state.states) != len(definitions):
        raise ValueError('Correa STMG requires a reading for each definition')
    if metric.color_kpi_key is not None and state.metric_color is None:
        raise ValueError('Configured Correa STMG color requires a reading')
    return html.Section(
        [
            html.H3('CORREAS STMG', className='ada-io-correas-stmg__title'),
            html.Div(
                [_image(item, reading) for item, reading in zip(definitions, state.states, strict=True)],
                className='ada-io-correas-stmg__items',
            ),
            _metric(metric, state.metric, state.metric_color),
        ],
        className='ada-io-correas-stmg',
    )


def _image(definition: CorreaStmgDefinition, state: DisplayValue) -> Component:
    return html.Div(
        build_equipment_state_image(
            EquipmentStateImage(
                image='correa_stmg',
                state=state,
                label=definition.label,
                label_position=LabelPosition.BOTTOM,
                label_class_name='ada-io-correas-stmg__label',
                image_class_name='ada-io-correas-stmg__image',
            )
        ),
        className='ada-io-correas-stmg__item',
        role='button',
        tabIndex=0,
        title=definition.state_kpi_key,
        **{'data-kpi-inspection-key': definition.state_kpi_key},
    )


def _metric(
    metric: CorreaStmgMetricDefinition,
    value: DisplayValue,
    color: DisplayValue | None,
) -> Component:
    tone = InlineValueRowTone.DEFAULT
    if color is not None and color.status is DisplayStatus.OK:
        tone = _TONES[color.value]
    shown: str | Component
    if value.status is DisplayStatus.OK:
        shown = str(value.value)
    else:
        icon = build_display_status_icon(
            value.status, class_name='ada-io-correas-stmg__status-icon'
        )
        if icon is None:
            raise ValueError('Correa STMG metric status icon cannot be resolved')
        shown = icon
    row = build_inline_value_row(
        InlineValueRowState(
            definition=InlineValueRowDefinition(metric.label, unit=metric.unit),
            value=shown,
            tone=tone,
            class_name='ada-io-correas-stmg__row',
        )
    )
    children: list[Component] = [html.Div(
        row,
        className='ada-io-correas-stmg__value-target',
        role='button',
        tabIndex=0,
        title=metric.value_kpi_key,
        **{'data-kpi-inspection-key': metric.value_kpi_key},
    )]
    if metric.color_kpi_key is not None:
        if color is None:
            raise ValueError('Correa STMG metric color cannot be missing')
        children.append(_color_indicator(color, metric.color_kpi_key))
    return html.Div(children, className='ada-io-correas-stmg__metric')


def _color_indicator(color: DisplayValue, key: str) -> Component:
    classes = 'ada-io-correas-stmg__color-indicator'
    if color.status is DisplayStatus.OK:
        tone = _TONES[color.value]
        classes += f' ada-io-correas-stmg__color-indicator--{tone.value}'
        content = html.Span(className='ada-io-correas-stmg__color-dot', **{'aria-hidden': 'true'})
    else:
        content = build_display_status_icon(
            color.status, class_name='ada-io-correas-stmg__status-icon'
        )
        if content is None:
            raise ValueError('Correa STMG color status icon cannot be resolved')
    return html.Span(
        content,
        className=classes,
        role='button',
        tabIndex=0,
        title=key,
        **{'data-kpi-inspection-key': key},
    )
