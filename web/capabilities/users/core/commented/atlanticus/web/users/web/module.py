# Espejo pedagógico: Users Administration conserva identidad de origen y limita edición a profile y enabled.
from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule
from atlanticus.web.users.web.callbacks import register_users_admin_callbacks
from atlanticus.web.users.web.models import UsersAdminWebContext


def create_users_admin_web_module(context: UsersAdminWebContext) -> WebModule:
    def register_callbacks(app: object, _services: object) -> None:
        register_users_admin_callbacks(app, context)

    return WebModule(
        name='atlanticus-users-administration',
        asset_layers=(
            AssetLayer(
                name='atlanticus_users_administration',
                load_order=718,
                package='atlanticus.web.users',
            ),
        ),
        register_callbacks=register_callbacks,
    )
