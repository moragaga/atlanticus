from __future__ import annotations

from collections.abc import Mapping

from dash import dcc, html
from dash.development.base_component import Component

from ada.configuration.branding import BrandingConfiguration
from ada.web.configuration.manager_tools.ids import (
    BRANDING_CONFIGURATION_STORE_ID,
    BRANDING_DRAFT_STORE_ID,
    BRANDING_STATUS_ID,
    BRANDING_VARIANT_ID,
    ROOT_ID,
)
from ada.web.configuration.manager_tools.models import branding_variant_options
from ada.web.configuration.tool_editor import build_tool_configuration_editor


def build_manager_tools_page(
    *,
    tool_configuration_document: Mapping[str, object] | None = None,
    branding_configuration_document: Mapping[str, object] | None = None,
) -> Component:
    branding_document = (
        dict(branding_configuration_document)
        if branding_configuration_document is not None
        else BrandingConfiguration().to_document()
    )
    return html.Main(
        [
            dcc.Store(
                id=BRANDING_CONFIGURATION_STORE_ID,
                data=branding_document,
                storage_type='memory',
            ),
            dcc.Store(id=BRANDING_DRAFT_STORE_ID, data=None, storage_type='memory'),
            _page_heading(),
            _branding_section(),
            build_tool_configuration_editor(
                configuration_document=tool_configuration_document,
            ),
        ],
        id=ROOT_ID,
        className='ada-manager-tools',
        **{'data-ada-manager-tools': 'true'},
    )


def _page_heading() -> Component:
    return html.Header(
        [
            html.P('Manager · Tools', className='ada-manager-tools__eyebrow'),
            html.H1('Configuración de Tool', className='ada-manager-tools__title'),
            html.P(
                (
                    'Edita la configuración funcional de la Tool sin mezclar persistencia '
                    'ni proyección.'
                ),
                className='ada-manager-tools__copy',
            ),
        ],
        className='ada-manager-tools__heading',
    )


def _branding_section() -> Component:
    return html.Section(
        [
            html.Div(
                [
                    html.H3('Branding', className='ada-manager-tools__section-title'),
                    html.P(
                        (
                            'La variante es manual y permanece activa hasta que se cambie '
                            'desde el Manager.'
                        ),
                        className='ada-manager-tools__section-copy',
                    ),
                ],
                className='ada-manager-tools__section-heading',
            ),
            html.Label(
                [
                    html.Span('Variante del logo', className='ada-manager-tools__field-label'),
                    dcc.Dropdown(
                        id=BRANDING_VARIANT_ID,
                        options=list(branding_variant_options()),
                        clearable=False,
                        searchable=False,
                        className='ada-manager-tools__branding-select',
                    ),
                    html.Small(
                        'No existe activación automática por fecha.',
                        className='ada-manager-tools__help',
                    ),
                ],
                className='ada-manager-tools__field',
            ),
            html.Div(
                id=BRANDING_STATUS_ID,
                className='ada-manager-tools__status',
                role='status',
            ),
        ],
        className='ada-manager-tools__section',
    )
