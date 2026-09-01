from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule
from atlanticus.web.users.configuration.web.callbacks import register_users_admin_callbacks
from atlanticus.web.users.configuration.web.models import UsersAdminWebContext


def create_users_admin_web_module(context: UsersAdminWebContext) -> WebModule:
    def register_callbacks(app: object, _services: object) -> None:
        register_users_admin_callbacks(app, context)

    return WebModule(
        name='atlanticus-users-configuration',
        asset_layers=(
            AssetLayer(
                name='atlanticus_users_configuration',
                load_order=705,
                package='atlanticus.web.users.configuration',
            ),
        ),
        register_callbacks=register_callbacks,
    )
