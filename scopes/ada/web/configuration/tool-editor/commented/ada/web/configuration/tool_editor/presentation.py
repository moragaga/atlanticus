from __future__ import annotations

# Presentación reusable de la sección Sources de una Tool.
# No incluye navegación, persistencia ni shell de Manager; esas responsabilidades se componen fuera.

from collections.abc import Mapping

from dash import dcc, html
from dash.development.base_component import Component

from ada.web.configuration.tool_editor.ids import (
    ADDITIONAL_OBSERVATION_ID,
    CONFIGURATION_STORE_ID,
    DISPATCH_DEGRADING_ID,
    DISPATCH_ENABLED_ID,
    DISPATCH_FIELDS_ID,
    DISPATCH_PRE_DEGRADING_ID,
    DRAFT_STORE_ID,
    PI_DEGRADING_ID,
    PI_PRE_DEGRADING_ID,
    ROOT_ID,
    VALIDATION_MESSAGE_ID,
    VALIDITY_STORE_ID,
)


def build_tool_source_editor(
    *,
    configuration_document: Mapping[str, object] | None = None,
) -> Component:
    initial_document = dict(configuration_document) if configuration_document is not None else None
    return html.Section(
        [
            dcc.Store(
                id=CONFIGURATION_STORE_ID,
                data=initial_document,
                storage_type='memory',
            ),
            dcc.Store(id=DRAFT_STORE_ID, data=None, storage_type='memory'),
            dcc.Store(id=VALIDITY_STORE_ID, data=False, storage_type='memory'),
            _heading(),
            _control_source(
                title='PI',
                subtitle='Fuente principal · CONTROL obligatorio',
                pre_degrading_id=PI_PRE_DEGRADING_ID,
                degrading_id=PI_DEGRADING_ID,
            ),
            html.Div(
                [
                    dcc.Checklist(
                        id=DISPATCH_ENABLED_ID,
                        options=[
                            {
                                'label': 'Usar Dispatch',
                                'value': 'dispatch',
                            }
                        ],
                        value=[],
                        className='ada-tool-source-editor__dispatch-toggle',
                    ),
                    html.Div(
                        _threshold_fields(
                            pre_degrading_id=DISPATCH_PRE_DEGRADING_ID,
                            degrading_id=DISPATCH_DEGRADING_ID,
                        ),
                        id=DISPATCH_FIELDS_ID,
                        hidden=True,
                        className='ada-tool-source-editor__threshold-grid',
                    ),
                ],
                className='ada-tool-source-editor__source-card',
                **{'data-source-key': 'dispatch'},
            ),
            _additional_observation(),
            html.Div(
                id=VALIDATION_MESSAGE_ID,
                className='ada-tool-source-editor__validation',
                role='status',
            ),
        ],
        id=ROOT_ID,
        className='ada-tool-source-editor',
        **{'data-ada-tool-source-editor': 'true'},
    )


def _heading() -> Component:
    return html.Div(
        [
            html.H3('Fuentes', className='ada-tool-source-editor__title'),
            html.P(
                (
                    'PI es la fuente CONTROL principal. Dispatch es opcional. '
                    'Las observaciones adicionales describen fuentes consumidas que no '
                    'participan en la degradación de la herramienta.'
                ),
                className='ada-tool-source-editor__copy',
            ),
        ],
        className='ada-tool-source-editor__heading',
    )


def _control_source(
    *,
    title: str,
    subtitle: str,
    pre_degrading_id: str,
    degrading_id: str,
) -> Component:
    return html.Div(
        [
            html.Div(
                [
                    html.Strong(title),
                    html.Span(subtitle),
                ],
                className='ada-tool-source-editor__source-heading',
            ),
            html.Div(
                _threshold_fields(
                    pre_degrading_id=pre_degrading_id,
                    degrading_id=degrading_id,
                ),
                className='ada-tool-source-editor__threshold-grid',
            ),
        ],
        className='ada-tool-source-editor__source-card',
        **{'data-source-key': title.casefold()},
    )


def _threshold_fields(
    *,
    pre_degrading_id: str,
    degrading_id: str,
) -> list[Component]:
    return [
        _number_field(
            label='Pre-degrading',
            component_id=pre_degrading_id,
            help_text='Segundos sin actualización antes de entrar en alerta preventiva.',
        ),
        _number_field(
            label='Degrading',
            component_id=degrading_id,
            help_text='Segundos sin actualización antes de degradar la aplicación.',
        ),
    ]


def _number_field(*, label: str, component_id: str, help_text: str) -> Component:
    return html.Label(
        [
            html.Span(label, className='ada-tool-source-editor__field-label'),
            html.Div(
                [
                    dcc.Input(
                        id=component_id,
                        type='number',
                        min=1,
                        step=1,
                        debounce=True,
                        className='ada-tool-source-editor__number-input',
                    ),
                    html.Span('s', className='ada-tool-source-editor__unit'),
                ],
                className='ada-tool-source-editor__number-control',
            ),
            html.Small(help_text, className='ada-tool-source-editor__help'),
        ],
        className='ada-tool-source-editor__field',
    )


def _additional_observation() -> Component:
    return html.Div(
        [
            html.Div(
                [
                    html.Strong('Observaciones adicionales'),
                    html.Span('ADDITIONAL OBSERVATION'),
                ],
                className='ada-tool-source-editor__source-heading',
            ),
            dcc.Textarea(
                id=ADDITIONAL_OBSERVATION_ID,
                placeholder='source_key_adicional',
                className='ada-tool-source-editor__textarea',
            ),
            html.Small(
                (
                    'Ingresa una source_key por línea o separada por coma. '
                    'Estas fuentes se agregan al consumo y a OBSERVATION, pero no a CONTROL.'
                ),
                className='ada-tool-source-editor__help',
            ),
        ],
        className='ada-tool-source-editor__source-card',
    )
