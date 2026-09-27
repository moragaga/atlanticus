# El branding ADA se inyecta por composición, sin acoplar Manager con logos de la herramienta.
from __future__ import annotations

from atlanticus.web.assets import AssetLayer
from atlanticus.web.manager import ManagerHeaderBrandMark
from atlanticus.web.manager.web.assets import manager_asset_layer
from atlanticus.web.modules import WebModule

ADA_MANAGER_BRAND_ASSETS = AssetLayer(
    name='ada_configuration_manager_brand',
    load_order=680,
    package='ada.web.application.configuration_manager',
)


def build_ada_manager_brand_marks() -> tuple[ManagerHeaderBrandMark, ...]:
    # Cada propietario publica sus imágenes como recursos empaquetados.
    application = f'/assets/{ADA_MANAGER_BRAND_ASSETS.target_name}/img'
    framework = f'/assets/{manager_asset_layer().target_name}/img'
    return (
        ManagerHeaderBrandMark(
            role='product',
            logo_src=f'{application}/ada-operational-secondary.svg',
            logo_alt='ADA',
        ),
        ManagerHeaderBrandMark(
            role='framework',
            logo_src=f'{framework}/atlanticus-primary.webp',
            logo_alt='Atlanticus Framework',
        ),
    )


def create_ada_manager_brand_module() -> WebModule:
    return WebModule(
        name='ada-configuration-manager-brand',
        asset_layers=(ADA_MANAGER_BRAND_ASSETS,),
    )
