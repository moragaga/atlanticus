from __future__ import annotations

# La UI reutilizable dibuja lecturas y siluetas sin conocer KPI keys, Collector ni Tool.

from dash import html
from dash.development.base_component import Component

from ada.web.ui.display_status import DisplayStatus, build_display_status_icon

from .models import StockpileItem, StockpilePanel
from .svg import build_stockpile_data_uri
from .values import StockpileReading, resolve_stockpile_reading


# Se presenta un conjunto de pilas; nombre, orden y escala vienen del desarrollador.
def build_stockpile_panel(panel: StockpilePanel) -> Component:
    if not isinstance(panel, StockpilePanel):
        raise TypeError('panel must be StockpilePanel')
    return html.Div(
        className=_classes('ada-stockpile', panel.class_name),
        children=[_build_item(item, panel) for item in panel.items],
    )


# Cada lectura se resuelve independientemente y nunca se inventa una lectura ausente.
def _build_item(item: StockpileItem, panel: StockpilePanel) -> Component:
    percentage = resolve_stockpile_reading(item.percentage, percentage=True)
    height = resolve_stockpile_reading(item.height_m, percentage=False)
    return html.Div(
        className=_classes('ada-stockpile__item', panel.item_class_name),
        children=[
            html.Span(
                item.label, className=_classes('ada-stockpile__label', panel.label_class_name)
            ),
            _build_graphic(height, panel),
            html.Div(
                className='ada-stockpile__values',
                children=[
                    _build_reading(percentage, unit='%', class_name=panel.value_class_name),
                    (
                        _build_reading(height, unit='m', class_name=panel.value_class_name)
                        if height.status is DisplayStatus.OK
                        else None
                    ),
                ],
            ),
        ],
    )


# Si no hay altura válida aparece el icono del sistema en vez de un dibujo con altura falsa.
def _build_graphic(height: StockpileReading, panel: StockpilePanel) -> Component:
    if height.status is not DisplayStatus.OK:
        return html.Div(
            _status_icon(height.status),
            className=_classes('ada-stockpile__graphic', panel.graphic_class_name),
        )
    if height.number is None:
        raise ValueError('Valid stockpile height requires numeric value')
    return html.Img(
        src=build_stockpile_data_uri(height.number, scale_max_m=panel.scale_max_m),
        alt='',
        draggable=False,
        className=_classes('ada-stockpile__graphic', panel.graphic_class_name),
        **{'aria-hidden': 'true'},
    )


# Los textos originales se conservan; las unidades se presentan fuera del dato numérico.
def _build_reading(reading: StockpileReading, *, unit: str, class_name: str | None) -> Component:
    content = (
        [reading.text, unit]
        if reading.status is DisplayStatus.OK
        else [_status_icon(reading.status)]
    )
    return html.Span(
        children=content,
        className=_classes('ada-stockpile__value', class_name),
    )


# Reutilizamos los iconos existentes de display-status para todos los fallos.
def _status_icon(status: DisplayStatus) -> Component:
    icon = build_display_status_icon(status, class_name='ada-stockpile__status-icon')
    if icon is None:
        raise ValueError('Stockpile status icon cannot be resolved')
    return icon


# Las clases extra son opcionales y no tienen efecto sobre semántica ni geometría.
def _classes(base: str, custom: str | None) -> str:
    return ' '.join(part for part in (base, custom) if part)
