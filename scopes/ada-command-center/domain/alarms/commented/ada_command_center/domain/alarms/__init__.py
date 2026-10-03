# Este package conserva únicamente identidad y política propias de Command Center.
# Los contratos publicados de Alarmas viven en ada.contracts.alarms.

from ada_command_center.domain.alarms.identity import ALARM_CONFIGURATION_SOURCE_KEY
from ada_command_center.domain.alarms.routing_policy import next_routing_tool_kind

__version__ = '1.0.0'

__all__ = [
    'ALARM_CONFIGURATION_SOURCE_KEY',
    'next_routing_tool_kind',
    '__version__',
]
