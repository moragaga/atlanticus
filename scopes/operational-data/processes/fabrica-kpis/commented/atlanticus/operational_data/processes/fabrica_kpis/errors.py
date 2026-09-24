# Espejo pedagógico: misma ejecución y contratos que el archivo productivo.
# Contrato de FabricaProcessError.
class FabricaProcessError(RuntimeError):
    pass


# Contrato de FabricaProcessConfigurationError.
class FabricaProcessConfigurationError(FabricaProcessError):
    pass
