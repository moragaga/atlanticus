# Error de dominio para fallos de lectura o publicación del Source de Tool.
class ToolConfigurationSourceError(RuntimeError):
    pass


# Error de dominio para una proyección de Tool que no puede construirse.
class ToolConfigurationProjectionError(RuntimeError):
    pass
