# Jerarquía mínima de errores del Tool Catalog.
# Se separan validación, codec, Storage y consolidación para conservar diagnósticos claros.
# Los mensajes productivos permanecen en inglés según el contrato del proyecto.

class ToolCatalogError(Exception):
    pass


class ToolCatalogValidationError(ToolCatalogError):
    pass


class ToolCatalogCodecError(ToolCatalogError):
    pass


class ToolCatalogStoreError(ToolCatalogError):
    pass


class ToolCatalogConsolidationError(ToolCatalogError):
    pass
