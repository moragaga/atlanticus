from __future__ import annotations

from ada.web.configuration import ADA_CONFIGURATION_ASSET_LAYER
from ada.web.kpis.configuration.web.callbacks import (
    register_kpi_configuration_editor_callbacks,
)
from ada.web.kpis.configuration.web.models import KpiConfigurationEditorContext
from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

ADA_KPI_CONFIGURATION_EDITOR_ASSET_LAYER = AssetLayer(
    name='ada_kpi_configuration_editor',
    load_order=170,
    package='ada.web.kpis.configuration.web',
)


def create_kpi_configuration_editor_module(
    context: KpiConfigurationEditorContext | None = None,
) -> WebModule:
    def register_callbacks(app: object, _services: object) -> None:
        if context is not None:
            register_kpi_configuration_editor_callbacks(app, context)

    return WebModule(
        name='ada-kpi-configuration',
        asset_layers=(
            ADA_CONFIGURATION_ASSET_LAYER,
            ADA_KPI_CONFIGURATION_EDITOR_ASSET_LAYER,
        ),
        register_callbacks=register_callbacks if context is not None else None,
    )
