from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from dash import Input, Output, State, html
from dash.exceptions import PreventUpdate

from ada.web.alarms.collector import alarm_live_store_id
from ada.web.alarms.live_surface import (
    ADA_ALARM_LIVE_SURFACE_ASSET_LAYER,
    ALARM_LIVE_BOARD_ID,
    build_live_alarm_cards,
    resolve_live_alarm_capacity,
)
from atlanticus.web.models import WebApplicationDefinition
from atlanticus.web.modules import WebModule


def attach_operational_alarm_surface(
    definition: WebApplicationDefinition, *, tool_key: str,
    can_view: Callable[[], bool] | None = None,
    component_keys: tuple[str, ...] = (),
) -> WebApplicationDefinition:
    if not isinstance(definition, WebApplicationDefinition):
        raise TypeError('Alarm surface requires WebApplicationDefinition')
    if any(module.name == 'ada-alarm-live-surface' for module in definition.modules):
        raise ValueError('Alarm surface is already attached')
    if can_view is not None and not callable(can_view):
        raise TypeError('Alarm surface authorization must be callable')
    store_id = alarm_live_store_id(tool_key)

    def register_callbacks(dash_app, _services) -> None:
        @dash_app.callback(
            Output(ALARM_LIVE_BOARD_ID, 'children'),
            Output(ALARM_LIVE_BOARD_ID, 'style'),
            Output(ALARM_LIVE_BOARD_ID, 'data-ready'),
            Input(store_id, 'modified_timestamp'),
            State(store_id, 'data'),
        )
        def render_alarm_live(_modified_timestamp: int | None, data: object):
            if can_view is not None and not can_view():
                return [], {'--ada-alarm-live-slot-count': '1'}, 'true'
            if (
                not isinstance(data, dict)
                or data.get('availability') not in {
                    'ready', 'empty', 'retired', 'missing', 'container_missing',
                    'invalid', 'unavailable'
                }
            ):
                raise PreventUpdate
            rendered = list(build_live_alarm_cards(
                data, tool_key=tool_key, component_keys=component_keys,
            ))
            availability = data['availability']
            has_actual_cards = bool(rendered)
            if not rendered:
                captions = {
                    'empty': 'Sin alarmas activas',
                    'missing': 'No existe una publicacion de alarmas',
                    'container_missing': 'Contenedor de alarmas no disponible',
                    'invalid': 'Publicacion de alarmas invalida',
                    'unavailable': 'No se pudo consultar alarmas',
                    'retired': 'Alarmas retiradas',
                }
                message = captions.get(availability, 'Sin alarmas activas')
                rendered = [html.Div(message, role='status', className='ada-alarm-live-status')]
            if has_actual_cards and availability not in {'ready', 'empty'}:
                rendered.insert(0, html.Div(
                    'Mostrando alarmas de una publicacion anterior',
                    role='status',
                    **{'data-ada-alarm-source-stale': 'true'},
                ))
            return (
                rendered,
                {'--ada-alarm-live-slot-count': str(resolve_live_alarm_capacity(
                    data, tool_key=tool_key,
                ))},
                'true',
            )

    return replace(
        definition,
        modules=(*definition.modules, WebModule(
            name='ada-alarm-live-surface',
            asset_layers=(ADA_ALARM_LIVE_SURFACE_ASSET_LAYER,),
            register_callbacks=register_callbacks,
        )),
    )
