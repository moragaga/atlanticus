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
