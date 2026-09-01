from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule
from atlanticus.web.navigation.configuration.web.callbacks import (
    register_navigation_admin_callbacks,
)
from atlanticus.web.navigation.configuration.web.models import NavigationAdminWebContext


# Resuelve `create navigation admin web module` manteniendo validación y estado explícitos.
def create_navigation_admin_web_module(context: NavigationAdminWebContext) -> WebModule:
    # Resuelve `register callbacks` manteniendo validación y estado explícitos.
    def register_callbacks(app: object, _services: object) -> None:
        register_navigation_admin_callbacks(app, context)

    return WebModule(
        name='atlanticus-navigation-configuration',
        asset_layers=(
            AssetLayer(
                name='atlanticus_navigation_configuration',
                load_order=715,
                package='atlanticus.web.navigation.configuration',
            ),
        ),
        register_callbacks=register_callbacks,
    )
