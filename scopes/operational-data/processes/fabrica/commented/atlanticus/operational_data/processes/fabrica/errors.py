# Espejo comentado del proceso Operational Data Fábrica. La lógica ejecutable es idéntica al source productivo; este archivo existe para revisión en español.
class FabricaProcessError(RuntimeError):
    pass


class FabricaProcessConfigurationError(FabricaProcessError):
    pass
