from __future__ import annotations

from dataclasses import replace

from dash import Input, Output

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
) -> WebApplicationDefinition:
    if not isinstance(definition, WebApplicationDefinition):
        raise TypeError('Alarm surface requires WebApplicationDefinition')
    if any(module.name == 'ada-alarm-live-surface' for module in definition.modules):
        raise ValueError('Alarm surface is already attached')
    store_id = alarm_live_store_id(tool_key)

    def register_callbacks(dash_app, _services) -> None:
        @dash_app.callback(
            Output(ALARM_LIVE_BOARD_ID, 'children'),
            Output(ALARM_LIVE_BOARD_ID, 'style'),
            Input(store_id, 'data'),
        )
        def render_alarm_live(data: object):
            return (
                list(build_live_alarm_cards(data, tool_key=tool_key)),
                {'--ada-alarm-live-slot-count': str(resolve_live_alarm_capacity(
                    data, tool_key=tool_key,
                ))},
            )

    return replace(
        definition,
        modules=(*definition.modules, WebModule(
            name='ada-alarm-live-surface',
            asset_layers=(ADA_ALARM_LIVE_SURFACE_ASSET_LAYER,),
            register_callbacks=register_callbacks,
        )),
    )
