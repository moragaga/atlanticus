# Espejo comentado de presentación del Tool Editor R2.

from __future__ import annotations

from collections.abc import Mapping

from dash import dcc, html
from dash.development.base_component import Component

from ada.configuration.tools import BrandingVariant, ToolConfigurationKind
from ada.web.configuration.tool_editor.ids import (
    BRANDING_ID,
    CONFIGURATION_STORE_ID,
    COVERAGE_ID,
    DISPATCH_DEGRADATION_ID,
    DISPATCH_DEGRADATION_WRAPPER_ID,
    DISPATCH_ENABLED_ID,
    DISPATCH_PREVENTIVE_ID,
    DISPLAY_NAME_ID,
    DRAFT_STORE_ID,
    KIND_ID,
    PI_DEGRADATION_ID,
    PI_PREVENTIVE_ID,
    PROCESS_COVERAGE_STORE_ID,
    ROOT_ID,
    TOOL_KEY_STORE_ID,
    VALIDATION_MESSAGE_ID,
    VALIDITY_STORE_ID,
)


def build_tool_source_editor(
    *,
    configuration_document: Mapping[str, object] | None = None,
) -> Component:
    initial_document = (
        dict(configuration_document)
        if configuration_document is not None
        else None
    )
    return html.Div(
        [
            dcc.Store(
                id=CONFIGURATION_STORE_ID,
                data=initial_document,
                storage_type='memory',
            ),
            dcc.Store(id=DRAFT_STORE_ID, data=None, storage_type='memory'),
            # Conserva la identidad generada aunque cambie nombre o tipo.
            dcc.Store(
                id=TOOL_KEY_STORE_ID,
                data=(
                    initial_document.get('tool_key')
                    if initial_document is not None
                    else None
                ),
                storage_type='memory',
            ),
            dcc.Store(id=VALIDITY_STORE_ID, data=False, storage_type='memory'),
            # Mantiene la cobertura Process al alternar temporalmente a Integrated.
            dcc.Store(
                id=PROCESS_COVERAGE_STORE_ID,
                data=None,
                storage_type='memory',
            ),
            _general_section(),
            _source_state_section(),
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


def _general_section() -> Component:
    return html.Section(
        [
            _section_heading(
                'Información general',
                (
                    'Define la identidad, el tipo de aplicación, '
                    'su cobertura operacional y el branding activo.'
                ),
            ),
            html.Div(
                [
                    _text_field(
                        label='Nombre de la herramienta',
                        component_id=DISPLAY_NAME_ID,
                        placeholder='Operaciones Integradas',
                    ),
                    _select_field(
                        label='Tipo de herramienta',
                        component_id=KIND_ID,
                        options=[
                            {
                                'label': 'Procesos',
                                'value': ToolConfigurationKind.PROCESS.value,
                            },
                            {
                                'label': 'Operaciones integradas',
                                'value': (
                                    ToolConfigurationKind
                                    .INTEGRATED_OPERATIONS
                                    .value
                                ),
                            },
                        ],
                        placeholder='Seleccionar tipo',
                    ),
                    _select_field(
                        label='Cobertura operacional',
                        component_id=COVERAGE_ID,
                        options=[],
                        placeholder='Selecciona primero el tipo',
                        disabled=True,
                    ),
                    _select_field(
                        label='Branding',
                        component_id=BRANDING_ID,
                        options=[
                            {
                                'label': 'Normal',
                                'value': BrandingVariant.ORIGINAL.value,
                            },
                            {
                                'label': 'Fiestas Patrias',
                                'value': BrandingVariant.FIESTAS_PATRIAS.value,
                            },
                            {
                                'label': 'Mes de la Minería',
                                'value': BrandingVariant.MINING_MONTH.value,
                            },
                            {
                                'label': 'Navidad',
                                'value': BrandingVariant.CHRISTMAS.value,
                            },
                            {
                                'label': 'Año Nuevo',
                                'value': BrandingVariant.NEW_YEAR.value,
                            },
                        ],
                        placeholder='Seleccionar branding',
                    ),
                ],
                className='ada-tool-source-editor__general-grid',
            ),
        ],
        className='ada-tool-source-editor__section',
    )


def _source_state_section() -> Component:
    return html.Section(
        [
            _section_heading(
                'Estado de fuentes',
                (
                    'PI determina el estado operacional de la herramienta. '
                    'Dispatch puede participar opcionalmente y mantiene '
                    'umbrales preventivo y de degradación propios.'
                ),
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Strong('PI'),
                                    html.Span('Fuente principal · obligatoria'),
                                ],
                                className='ada-tool-source-editor__source-heading',
                            ),
                            html.Div(
                                [
                                    _number_field(
                                        label='Umbral preventivo',
                                        component_id=PI_PREVENTIVE_ID,
                                        help_text=(
                                            'Segundos sin actualización antes '
                                            'de entrar en alerta preventiva.'
                                        ),
                                    ),
                                    _number_field(
                                        label='Umbral de degradación',
                                        component_id=PI_DEGRADATION_ID,
                                        help_text=(
                                            'Segundos sin actualización antes '
                                            'de degradar la herramienta.'
                                        ),
                                    ),
                                ],
                                className='ada-tool-source-editor__threshold-grid',
                            ),
                        ],
                        className=(
                            'ada-tool-source-editor__source-card '
                            'ada-tool-source-editor__source-card--primary'
                        ),
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
                            # Dispatch muestra el mismo par de umbrales que PI, pero con valores propios.
                            html.Div(
                                html.Div(
                                    [
                                        _number_field(
                                            label='Umbral preventivo',
                                            component_id=DISPATCH_PREVENTIVE_ID,
                                            help_text=(
                                                'Segundos sin actualización antes '
                                                'de entrar en alerta preventiva.'
                                            ),
                                        ),
                                        _number_field(
                                            label='Umbral de degradación',
                                            component_id=DISPATCH_DEGRADATION_ID,
                                            help_text=(
                                                'Segundos sin actualización antes '
                                                'de degradar la fuente Dispatch.'
                                            ),
                                        ),
                                    ],
                                    className='ada-tool-source-editor__threshold-grid',
                                ),
                                id=DISPATCH_DEGRADATION_WRAPPER_ID,
                                hidden=True,
                                className='ada-tool-source-editor__dispatch-threshold',
                            ),
                        ],
                        className='ada-tool-source-editor__dispatch-card',
                    ),
                ],
                className='ada-tool-source-editor__source-stack',
            ),
        ],
        className='ada-tool-source-editor__section',
    )


def _section_heading(title: str, copy: str) -> Component:
    return html.Div(
        [
            html.H3(title, className='ada-tool-source-editor__title'),
            html.P(copy, className='ada-tool-source-editor__copy'),
        ],
        className='ada-tool-source-editor__heading',
    )


def _text_field(
    *,
    label: str,
    component_id: str,
    placeholder: str,
) -> Component:
    return html.Label(
        [
            html.Span(label, className='ada-tool-source-editor__field-label'),
            dcc.Input(
                id=component_id,
                type='text',
                placeholder=placeholder,
                debounce=True,
                className='ada-tool-source-editor__text-input',
                style=_dash_input_style(),
            ),
        ],
        className='ada-tool-source-editor__field',
    )


def _select_field(
    *,
    label: str,
    component_id: str,
    options: list[dict[str, str]],
    placeholder: str,
    disabled: bool = False,
) -> Component:
    return html.Label(
        [
            html.Span(label, className='ada-tool-source-editor__field-label'),
            dcc.Dropdown(
                id=component_id,
                options=options,
                clearable=False,
                searchable=False,
                placeholder=placeholder,
                disabled=disabled,
                className='ada-tool-source-editor__select',
                style=_dash_select_style(),
            ),
        ],
        className='ada-tool-source-editor__field',
    )


def _number_field(
    *,
    label: str,
    component_id: str,
    help_text: str,
) -> Component:
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
                        style=_dash_input_style(),
                    ),
                    html.Span('s', className='ada-tool-source-editor__unit'),
                ],
                className='ada-tool-source-editor__number-control',
            ),
            html.Small(help_text, className='ada-tool-source-editor__help'),
        ],
        className='ada-tool-source-editor__field',
    )


def _dash_input_style() -> dict[str, str]:
    return {
        '--Dash-Stroke-Strong': 'var(--atlanticus-ui-primary)',
        '--Dash-Stroke-Weak': 'var(--atlanticus-ui-border)',
        '--Dash-Fill-Interactive-Strong': 'var(--atlanticus-ui-primary)',
        '--Dash-Fill-Interactive-Weak': 'var(--atlanticus-ui-selection-soft)',
        '--Dash-Fill-Inverse-Strong': 'var(--atlanticus-ui-surface)',
        '--Dash-Text-Primary': 'var(--atlanticus-ui-text)',
        '--Dash-Text-Strong': 'var(--atlanticus-ui-text)',
        '--Dash-Text-Weak': 'var(--atlanticus-ui-text-muted)',
        '--Dash-Text-Disabled': 'var(--atlanticus-ui-text-soft)',
        '--Dash-Fill-Primary-Hover': 'var(--atlanticus-ui-selection-soft)',
        '--Dash-Fill-Primary-Active': 'var(--atlanticus-ui-selection-soft)',
        '--Dash-Fill-Disabled': 'var(--atlanticus-ui-border)',
        '--Dash-Shading-Strong': 'rgb(7 21 34 / 25%)',
        '--Dash-Shading-Weak': 'rgb(7 21 34 / 12%)',
    }


def _dash_select_style() -> dict[str, str]:
    return {
        '--Dash-Spacing': '4px',
        '--Dash-Stroke-Strong': 'var(--atlanticus-ui-primary)',
        '--Dash-Stroke-Weak': 'var(--atlanticus-ui-border)',
        '--Dash-Fill-Interactive-Strong': 'var(--atlanticus-ui-primary)',
        '--Dash-Fill-Interactive-Weak': 'var(--atlanticus-ui-selection-soft)',
        '--Dash-Fill-Inverse-Strong': 'var(--atlanticus-ui-surface)',
        '--Dash-Text-Primary': 'var(--atlanticus-ui-text)',
        '--Dash-Text-Strong': 'var(--atlanticus-ui-text)',
        '--Dash-Text-Weak': 'var(--atlanticus-ui-text-muted)',
        '--Dash-Text-Disabled': 'var(--atlanticus-ui-text-soft)',
        '--Dash-Fill-Primary-Hover': 'var(--atlanticus-ui-selection-soft)',
        '--Dash-Fill-Primary-Active': 'var(--atlanticus-ui-selection-soft)',
        '--Dash-Fill-Disabled': 'var(--atlanticus-ui-border)',
        '--Dash-Shading-Strong': 'rgb(7 21 34 / 25%)',
        '--Dash-Shading-Weak': 'rgb(7 21 34 / 12%)',
    }
