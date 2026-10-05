# Errores públicos del contrato final de Operational Data.
from __future__ import annotations


class DataInputNotRequestedError(KeyError):
    pass


class DataColumnNotRequestedError(KeyError):
    pass
