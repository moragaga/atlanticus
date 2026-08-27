from __future__ import annotations

from dash import html
from dash.development.base_component import Component

from .models import (
    AlarmManagementSummaryArea,
    AlarmManagementSummarySegmentState,
    AlarmManagementSummaryState,
)

# Las etiquetas visibles pertenecen a la representación ADA, no al dominio de alarmas.
_AREA_LABELS = {
    AlarmManagementSummaryArea.MINE: 'Mina',
    AlarmManagementSummaryArea.PLANT: 'Planta',
}


def build_alarm_management_summary(
    state: AlarmManagementSummaryState | None,
) -> Component | None:
    # Sin estado no se fabrica placeholder; el slot del Header puede colapsar limpiamente.
    if state is None:
        return None
    return html.Div(
        className='ada-alarm-management-summary',
        children=[_build_segment(segment) for segment in state.segments],
    )


def _build_segment(segment: AlarmManagementSummarySegmentState) -> Component:
    area_label = _AREA_LABELS[segment.area]
    return html.Div(
        className='ada-alarm-management-summary__segment',
        **{
            'data-area': segment.area.value,
            'data-tone': segment.tone.value,
        },
        children=[
            html.Div(
                className='ada-alarm-management-summary__group',
                children=[
                    html.Span(
                        f'Grupo {area_label}',
                        className='ada-alarm-management-summary__label',
                    ),
                    html.Strong(
                        segment.group,
                        className=(
                            'ada-alarm-management-summary__value '
                            'ada-alarm-management-summary__group-value'
                        ),
                    ),
                ],
            ),
            html.Div(
                className='ada-alarm-management-summary__progress-block',
                children=[
                    html.Span(
                        f'Gestión {area_label}',
                        className='ada-alarm-management-summary__label',
                    ),
                    html.Strong(
                        f'{segment.management_percentage:g}%',
                        className=(
                            'ada-alarm-management-summary__value '
                            'ada-alarm-management-summary__percentage-value'
                        ),
                    ),
                    html.Progress(
                        value=segment.management_percentage,
                        max=100,
                        className='ada-alarm-management-summary__progress',
                        title=f'Gestión {area_label}: {segment.management_percentage:g}%',
                    ),
                ],
            ),
        ],
    )
