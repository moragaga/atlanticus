from __future__ import annotations

from enum import StrEnum


# Severidad de un valor individual, independiente del estado de disponibilidad.
class ValueSeverity(StrEnum):
    NEUTRAL = 'neutral'
    DANGER = 'danger'
    WARNING = 'warning'


def map_value_severity_code(value: object) -> ValueSeverity:
    # Los códigos del payload son cadenas literales. Ningún número es aceptado.
    if value is None or value == '0':
        return ValueSeverity.NEUTRAL
    if value == '1':
        return ValueSeverity.DANGER
    if value == '2':
        return ValueSeverity.WARNING
    raise ValueError('Value severity code must be "0", "1", "2" or null')
