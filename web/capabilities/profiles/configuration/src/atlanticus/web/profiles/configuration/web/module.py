from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule
from atlanticus.web.profiles.configuration.web.callbacks import register_profiles_admin_callbacks
from atlanticus.web.profiles.configuration.web.models import ProfilesAdminWebContext


def create_profiles_admin_web_module(context: ProfilesAdminWebContext) -> WebModule:
    def register_callbacks(app: object, _services: object) -> None:
        register_profiles_admin_callbacks(app, context)

    return WebModule(
        name='atlanticus-profiles-configuration',
        asset_layers=(
            AssetLayer(
                name='atlanticus_profiles_configuration',
                load_order=716,
                package='atlanticus.web.profiles.configuration',
            ),
        ),
        register_callbacks=register_callbacks,
    )
