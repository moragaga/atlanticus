# Registra únicamente los callbacks existentes y la capa CSS del editor de alarmas.
# El Manager genérico mantiene el ownership del workflow y su propio estilo.
from ada_command_center.web.alarms.configuration.web.callbacks import (
    register_alarm_configuration_admin_callbacks,
)
from ada_command_center.web.alarms.configuration.web.models import (
    AlarmConfigurationAdminWebContext,
)
from atlanticus.web.assets import AssetLayer
from atlanticus.web.modules import WebModule

# Se carga después de Manager: sólo contiene selectores propios del editor.
ALARM_CONFIGURATION_EDITOR_ASSET_LAYER = AssetLayer(
    name='ada_command_center_alarm_configuration_editor',
    load_order=350,
    package='ada_command_center.web.alarms.configuration.web',
)


def create_alarm_configuration_admin_web_module(
    context: AlarmConfigurationAdminWebContext,
) -> WebModule:
    def register_callbacks(app: object, _services: object) -> None:
        register_alarm_configuration_admin_callbacks(app, context)

    return WebModule(
        name='ada-command-center-alarm-configuration',
        asset_layers=(ALARM_CONFIGURATION_EDITOR_ASSET_LAYER,),
        register_callbacks=register_callbacks,
    )
