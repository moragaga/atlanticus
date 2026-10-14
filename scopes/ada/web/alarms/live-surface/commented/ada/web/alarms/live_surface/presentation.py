# La nueva superficie compone la baseline neutral con tablero y trazas vivas.
from __future__ import annotations

from dash import html

from ada.web.alarms.baseline_projection import AlarmBaselineProjection
from ada.web.alarms.baseline_surface import build_alarm_baseline_surface
from ada.web.alarms.live_surface.live import ALARM_LIVE_BOARD_ID


def build_alarm_live_surface(projection: AlarmBaselineProjection) -> html.Div:
    if not isinstance(projection, AlarmBaselineProjection):
        raise TypeError('Alarm Baseline Projection is required')
    # Los slots se reservan sin depender de que el collector haya publicado alarmas.
    return html.Div(
        [
            html.Div(
                id=ALARM_LIVE_BOARD_ID,
                className='ada-alarm-live-board',
                role='region',
                **{
                    'aria-label': 'Alarmas operacionales',
                    # La vista inicial ya reserva nueve columnas antes del primer render de JS.
                    **(
                        {'data-ada-alarm-layout': 'integrated',
                         'data-ada-alarm-presentation': 'overview'}
                        if projection.kind.value == 'integrated_operations' else {}
                    ),
                },
            ),
            build_alarm_baseline_surface(projection),
            html.Div(className='ada-alarm-live-routes', **{'aria-hidden': 'true'}),
        ],
        className='ada-alarm-live-surface',
        style={'--ada-alarm-live-component-count': (
            str(len(projection.main_points))
            if projection.kind.value == 'integrated_operations' else '6'
        )},
        **{'data-ada-alarm-live-tool-key': projection.tool_key},
    )
