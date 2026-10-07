# Errores propios de configuración y sesión del Alarm Runtime.
class AlarmRuntimeError(RuntimeError):
    pass


class AlarmRuntimeConfigurationError(AlarmRuntimeError):
    pass


class AlarmExecutionSessionError(AlarmRuntimeError):
    pass
