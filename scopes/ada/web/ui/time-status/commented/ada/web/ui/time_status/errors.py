# Error de definición local: evita filtrar ValueError genérico fuera de la capability.
class TimeStatusDefinitionError(ValueError):
    pass
