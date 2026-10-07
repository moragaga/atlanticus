class AlarmRuntimeError(RuntimeError):
    pass


class AlarmRuntimeConfigurationError(AlarmRuntimeError):
    pass


class AlarmExecutionSessionError(AlarmRuntimeError):
    pass
