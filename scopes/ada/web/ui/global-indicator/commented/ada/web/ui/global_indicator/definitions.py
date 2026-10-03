# Espejo pedagógico: las definiciones declaran qué representa el componente y qué KPI alimenta cada slot.
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .errors import GlobalIndicatorDefinitionError
from .models import global_indicator_measurement_capacity

_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')


# Cada fila conserva actual y plan; el color opcional pertenece sólo al valor actual.
@dataclass(frozen=True, slots=True)
class GlobalIndicatorMeasurementDefinition:
    key: str
    label: str
    actual_kpi_key: str
    plan_kpi_key: str
    color_kpi_key: str | None = None

    def __post_init__(self) -> None:
        _require_key(self.key, field_name='measurement key')
        _require_text(self.label, field_name='measurement label')
        object.__setattr__(
            self,
            'actual_kpi_key',
            _require_kpi_key(self.actual_kpi_key, field_name='actual_kpi_key'),
        )
        object.__setattr__(
            self,
            'plan_kpi_key',
            _require_kpi_key(self.plan_kpi_key, field_name='plan_kpi_key'),
        )
        if self.color_kpi_key is not None:
            object.__setattr__(
                self,
                'color_kpi_key',
                _require_kpi_key(self.color_kpi_key, field_name='color_kpi_key'),
            )

    @property
    def kpi_keys(self) -> tuple[str, ...]:
        keys = [self.actual_kpi_key, self.plan_kpi_key]
        if self.color_kpi_key is not None:
            keys.append(self.color_kpi_key)
        return tuple(keys)


# La última medición es un slot independiente y puede apuntar a un KPI distinto.
@dataclass(frozen=True, slots=True)
class GlobalIndicatorLastMeasurementDefinition:
    kpi_key: str
    key: str = 'latest'
    label: str = 'Última medición'

    def __post_init__(self) -> None:
        _require_key(self.key, field_name='last measurement key')
        _require_text(self.label, field_name='last measurement label')
        object.__setattr__(
            self,
            'kpi_key',
            _require_kpi_key(self.kpi_key, field_name='last measurement kpi_key'),
        )


# La definición es estática: describe identidad, textos, unidad y bindings; no contiene datos vivos.
@dataclass(frozen=True, slots=True)
class GlobalIndicatorDefinition:
    key: str
    label: str
    unit: str
    measurements: tuple[GlobalIndicatorMeasurementDefinition, ...]
    last_measurement: GlobalIndicatorLastMeasurementDefinition | None = None

    def __post_init__(self) -> None:
        measurements = tuple(self.measurements)
        object.__setattr__(self, 'measurements', measurements)
        _require_key(self.key, field_name='key')
        _require_text(self.label, field_name='label')
        _require_text(self.unit, field_name='unit')
        if not 2 <= len(measurements) <= global_indicator_measurement_capacity():
            raise GlobalIndicatorDefinitionError(
                'Global indicator definition requires two or three measurements'
            )
        if not all(isinstance(item, GlobalIndicatorMeasurementDefinition) for item in measurements):
            raise TypeError(
                'Global indicator definition measurements must contain '
                'GlobalIndicatorMeasurementDefinition values'
            )
        measurement_keys = tuple(item.key for item in measurements)
        if len(measurement_keys) != len(set(measurement_keys)):
            raise GlobalIndicatorDefinitionError(
                'Global indicator definition contains duplicate measurement keys'
            )
        if self.last_measurement is not None:
            if not isinstance(self.last_measurement, GlobalIndicatorLastMeasurementDefinition):
                raise TypeError(
                    'Global indicator last_measurement must be '
                    'GlobalIndicatorLastMeasurementDefinition or None'
                )
            if self.last_measurement.key in set(measurement_keys):
                raise GlobalIndicatorDefinitionError(
                    'Global indicator definition last measurement key must be unique'
                )

    # Expone las identidades necesarias para pedir datos, preservando orden y eliminando repetidos.
    @property
    def kpi_keys(self) -> tuple[str, ...]:
        keys = [key for measurement in self.measurements for key in measurement.kpi_keys]
        if self.last_measurement is not None:
            keys.append(self.last_measurement.kpi_key)
        return tuple(dict.fromkeys(keys))


# Permite al renderer resolver todos los KPI de una colección en una sola operación.
def global_indicator_kpi_keys(
    definitions: Iterable[GlobalIndicatorDefinition],
) -> tuple[str, ...]:
    resolved = tuple(definitions)
    if not all(isinstance(item, GlobalIndicatorDefinition) for item in resolved):
        raise TypeError('definitions must contain GlobalIndicatorDefinition values')
    return tuple(
        dict.fromkeys(key for definition in resolved for key in definition.kpi_keys)
    )


def _require_key(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or _KEY_PATTERN.fullmatch(value) is None:
        raise GlobalIndicatorDefinitionError(
            f'Invalid global indicator definition {field_name}: {value!r}'
        )


def _require_kpi_key(value: str, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f'Global indicator definition {field_name} must be a string')
    normalized = value.strip()
    if not normalized:
        raise GlobalIndicatorDefinitionError(
            f'Global indicator definition {field_name} cannot be empty'
        )
    return normalized


def _require_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise GlobalIndicatorDefinitionError(
            f'Global indicator definition {field_name} cannot be empty'
        )
