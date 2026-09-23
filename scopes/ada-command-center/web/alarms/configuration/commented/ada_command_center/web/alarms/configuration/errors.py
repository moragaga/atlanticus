# Error operacional del Source de Alarm Configuration.
class AlarmConfigurationSourceError(RuntimeError):
    pass


# Error de correlación entre un draft de alarmas y su catálogo Tools confirmado.
class AlarmConfigurationToolDependencyError(ValueError):
    pass
