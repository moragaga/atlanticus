# Espejo pedagógico de los contratos puros compartidos de datos operacionales.
from __future__ import annotations


class DataSourceNotRequestedError(KeyError):
    pass


# Señala que un consumidor intentó acceder a un input_key no declarado en su contrato.
class DataInputNotRequestedError(KeyError):
    pass


class DataColumnNotRequestedError(KeyError):
    pass
