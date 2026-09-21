from __future__ import annotations

import json

from dash import dcc, html

from ada_command_center.web.alarms.configuration.models import AlarmConfiguration
from ada_command_center.web.alarms.configuration.web.ids import (
    DOCUMENT_EDITOR_ID,
    DOCUMENT_STATUS_ID,
    IMPORT_RESULT_ID,
    IMPORT_UPLOAD_ID,
    MOUNT_STORE_ID,
    PROJECTION_NAME_ID,
    SAVE_BUTTON_ID,
    SAVE_RESULT_ID,
    SOURCE_NAME_ID,
)
from ada_command_center.web.alarms.configuration.web.models import (
    AlarmConfigurationAdminWebContext,
)


def build_alarm_configuration_admin(context: AlarmConfigurationAdminWebContext) -> object:
    empty = AlarmConfiguration(rules=(), messages=())
    return html.Div(
        [
            dcc.Store(id=MOUNT_STORE_ID, data=1, storage_type='memory'),
            _runtime_context(context),
            html.Section(
                [
                    html.H3('Alarm Configuration document'),
                    html.P(
                        'Document mode edits the complete Rules + Messages contract. '
                        'Validation, publication and projection use the Manager workflow.'
                    ),
                    dcc.Textarea(
                        id=DOCUMENT_EDITOR_ID,
                        value=json.dumps(
                            empty.to_document(),
                            ensure_ascii=False,
                            indent=2,
                            sort_keys=True,
                        ),
                        spellCheck=False,
                        style={'width': '100%', 'minHeight': '32rem', 'fontFamily': 'monospace'},
                    ),
                    html.Div(id=DOCUMENT_STATUS_ID),
                ]
            ),
            html.Section(
                [
                    html.Button(
                        'Save local draft',
                        id=SAVE_BUTTON_ID,
                        n_clicks=0,
                        type='button',
                    ),
                    html.Div(id=SAVE_RESULT_ID),
                ]
            ),
        ]
    )


def _runtime_context(context: AlarmConfigurationAdminWebContext) -> object:
    return html.Section(
        [
            html.Div(
                [
                    html.Span('Source'),
                    html.Strong(context.source_name, id=SOURCE_NAME_ID),
                ]
            ),
            html.Div(
                [
                    html.Span('Projection'),
                    html.Strong(context.projection_name, id=PROJECTION_NAME_ID),
                ]
            ),
            html.Div(
                [
                    dcc.Upload(
                        id=IMPORT_UPLOAD_ID,
                        children=html.Button('Import JSON', type='button'),
                        accept='.json,application/json',
                        multiple=False,
                    ),
                    html.Span(
                        'Import replaces the browser draft only after the contract is valid.'
                    ),
                    html.Div(id=IMPORT_RESULT_ID),
                ]
            ),
        ]
    )
