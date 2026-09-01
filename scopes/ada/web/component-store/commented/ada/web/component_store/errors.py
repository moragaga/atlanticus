# Error público propio del contrato Component Store.
# Mantenerlo separado evita filtrar errores internos de Tool Configuration.
class ComponentStoreValidationError(ValueError):
    pass
