from __future__ import annotations

from ada.web.configuration import ADA_CONFIGURATION_ASSET_LAYER
from ada.web.kpis.definition.web.callbacks import (
    register_kpi_definition_editor_callbacks,
)
from ada.web.kpis.definition.web.models import KpiDefinitionEditorContext
from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

ADA_KPI_DEFINITION_EDITOR_ASSET_LAYER = AssetLayer(
    name='ada_kpi_definition_editor',
    load_order=175,
    package='ada.web.kpis.definition.web',
)


def create_kpi_definition_editor_module(
    context: KpiDefinitionEditorContext | None = None,
    *,
    include_configuration_asset: bool = True,
) -> WebModule:
    def register_callbacks(app: object, _services: object) -> None:
        if context is not None:
            register_kpi_definition_editor_callbacks(app, context)

    asset_layers = (
        (ADA_CONFIGURATION_ASSET_LAYER, ADA_KPI_DEFINITION_EDITOR_ASSET_LAYER)
        if include_configuration_asset
        else (ADA_KPI_DEFINITION_EDITOR_ASSET_LAYER,)
    )
    return WebModule(
        name='ada-kpi-definition',
        asset_layers=asset_layers,
        register_callbacks=register_callbacks if context is not None else None,
    )
