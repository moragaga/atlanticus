# Preview de History para una release de Alarm Configuration.
# Resume el contenido sin reinterpretar ni resolver referencias externas.
from __future__ import annotations

from dash import html

from ada_command_center.web.alarms.configuration.models import AlarmConfiguration


def build_alarm_configuration_history_preview(payload: dict[str, object]) -> object:
    configuration = AlarmConfiguration.from_document(dict(payload))
    return html.Div(
        [
            _item('Rules', str(len(configuration.rules))),
            _item(
                'Active rules',
                str(sum(rule.is_active for rule in configuration.rules)),
            ),
            _item('Messages', str(len(configuration.messages))),
        ]
    )


def _item(label: str, value: str) -> object:
    return html.Div([html.Small(label), html.Strong(value)])
