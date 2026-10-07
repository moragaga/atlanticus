"""
Superficie pública del paquete ada.alarms.core.

El primer incremento expone únicamente los contratos de Core que necesita
Materialization. El resto del comportamiento del Engine se migrará en incrementos
posteriores sin depender del namespace de Command Center.
"""
from ada.alarms.core.models import (
    AlarmResolutionKey,
    AlarmRouting,
    DeactivationPolicy,
    PlannedAlarm,
    RoutingDestination,
)

__version__ = '1.0.0'

__all__ = [
    'AlarmResolutionKey',
    'AlarmRouting',
    'DeactivationPolicy',
    'PlannedAlarm',
    'RoutingDestination',
    '__version__',
]
