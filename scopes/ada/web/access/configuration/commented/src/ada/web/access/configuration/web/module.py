# WebModule registra assets y callbacks de ADA Access sin crear servicios de infraestructura.

from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

from ada.web.access.configuration.web.callbacks import register_ada_access_admin_callbacks
from ada.web.access.configuration.web.models import AdaAccessAdminWebContext


def create_ada_access_admin_web_module(context: AdaAccessAdminWebContext) -> WebModule:
    def register_callbacks(app: object, _services: object) -> None:
        register_ada_access_admin_callbacks(app, context)

    return WebModule(
        name='ada-access-configuration',
        asset_layers=(
            AssetLayer(
                name='ada_access_configuration',
                load_order=717,
                package='ada.web.access.configuration',
            ),
        ),
        register_callbacks=register_callbacks,
    )
