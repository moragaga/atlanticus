from __future__ import annotations

from dash import Input, Output

from ada.configuration.branding import BrandingConfiguration
from ada.web.configuration.manager_tools.ids import (
    BRANDING_CONFIGURATION_STORE_ID,
    BRANDING_DRAFT_STORE_ID,
    BRANDING_STATUS_ID,
    BRANDING_VARIANT_ID,
)
from ada.web.configuration.manager_tools.models import build_branding_draft


def register_manager_tools_callbacks(app: object) -> None:
    @app.callback(
        Output(BRANDING_VARIANT_ID, 'value'),
        Input(BRANDING_CONFIGURATION_STORE_ID, 'data'),
    )
    def load_branding_configuration(configuration_document: dict[str, object] | None):
        configuration = BrandingConfiguration.from_document(configuration_document or {})
        return configuration.variant.value

    @app.callback(
        Output(BRANDING_DRAFT_STORE_ID, 'data'),
        Output(BRANDING_STATUS_ID, 'children'),
        Input(BRANDING_VARIANT_ID, 'value'),
    )
    def build_branding_configuration_draft(variant_value: object):
        try:
            configuration = build_branding_draft(variant_value)
        except ValueError as error:
            return None, str(error)
        return configuration.to_document(), ''
