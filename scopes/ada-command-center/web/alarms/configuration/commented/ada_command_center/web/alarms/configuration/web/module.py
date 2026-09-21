# WebModule que registra los callbacks específicos de Alarm Configuration.
# No registra servicios aquí; la composición Manager agrega los servicios del dominio.
from ada_command_center.web.alarms.configuration.web.callbacks import (
    register_alarm_configuration_admin_callbacks,
)
from ada_command_center.web.alarms.configuration.web.models import (
    AlarmConfigurationAdminWebContext,
)
from atlanticus.web.modules import WebModule


def create_alarm_configuration_admin_web_module(
    context: AlarmConfigurationAdminWebContext,
) -> WebModule:
    def register_callbacks(app: object, _services: object) -> None:
        register_alarm_configuration_admin_callbacks(app, context)

    return WebModule(
        name='ada-command-center-alarm-configuration',
        register_callbacks=register_callbacks,
    )
