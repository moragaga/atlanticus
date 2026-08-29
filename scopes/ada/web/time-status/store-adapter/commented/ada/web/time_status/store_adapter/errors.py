# Errores explícitos para separar contrato físico inválido de un cruce de tool_key.
class TimeStatusStoreContractError(ValueError):
    pass


class TimeStatusToolScopeError(TimeStatusStoreContractError):
    pass
