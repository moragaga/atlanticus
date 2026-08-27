# Contratos visuales puros: no conocen Header, ToolManifest ni convenciones de claves KPI.
from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import TypeAlias

from dash.development.base_component import Component

from ada.web.ui.display_status import DisplayValue, coerce_display_value

from .errors import GlobalIndicatorDefinitionError

_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')
_CLASS_TOKEN = re.compile(r'^[A-Za-z_][A-Za-z0-9_-]*$')
_GLOBAL_INDICATOR_MEASUREMENT_CAPACITY = 3

IndicatorPrimitive: TypeAlias = str | int | float | Component
IndicatorInput: TypeAlias = IndicatorPrimitive | DisplayValue | None
IndicatorColorClass: TypeAlias = str | Component | None


@dataclass(frozen=True, slots=True)
class GlobalIndicatorStyle:
    heading_class: str = 'font-size-gi-300'
    measurement_label_class: str = 'font-size-gi-200'
    actual_value_class: str = 'font-size-gi-100'
    plan_value_class: str = 'font-size-gi-200'
    last_measurement_label_class: str = 'font-size-gi-400'
    last_measurement_value_class: str = 'font-size-gi-300'

    def __post_init__(self) -> None:
        for field_name in (
            'heading_class',
            'measurement_label_class',
            'actual_value_class',
            'plan_value_class',
            'last_measurement_label_class',
            'last_measurement_value_class',
        ):
            _require_class_tokens(getattr(self, field_name), field_name=field_name)


@dataclass(frozen=True, slots=True)
# Cada medición recibe valores ya resueltos por la composition/provider externo.
class GlobalIndicatorMeasurementState:
    key: str
    label: str
    actual_value: IndicatorInput
    plan_value: IndicatorInput
    color_class: IndicatorColorClass = None

    def __post_init__(self) -> None:
        _require_key(self.key, field_name='measurement key')
        _require_text(self.label, field_name='measurement label')
        object.__setattr__(self, 'actual_value', coerce_display_value(self.actual_value))
        object.__setattr__(self, 'plan_value', coerce_display_value(self.plan_value))


@dataclass(frozen=True, slots=True)
class GlobalIndicatorLastMeasurementState:
    actual_value: IndicatorInput
    key: str = 'latest'
    label: str = 'Última medición'
    color_class: IndicatorColorClass = None

    def __post_init__(self) -> None:
        _require_key(self.key, field_name='last measurement key')
        _require_text(self.label, field_name='last measurement label')
        object.__setattr__(self, 'actual_value', coerce_display_value(self.actual_value))


@dataclass(frozen=True, slots=True)
class GlobalIndicatorState:
    key: str
    label: str
    unit: str
    measurements: tuple[GlobalIndicatorMeasurementState, ...]
    last_measurement: GlobalIndicatorLastMeasurementState | None = None
    definition_key: str | None = None
    style: GlobalIndicatorStyle = field(default_factory=GlobalIndicatorStyle)

    def __post_init__(self) -> None:
        object.__setattr__(self, 'measurements', tuple(self.measurements))
        _require_key(self.key, field_name='key')
        _require_text(self.label, field_name='label')
        _require_text(self.unit, field_name='unit')
        if self.definition_key is not None:
            _require_key(self.definition_key, field_name='definition_key')
        # El estándar visual reserva hasta tres filas para mantener alineación entre indicadores.
        if not 2 <= len(self.measurements) <= _GLOBAL_INDICATOR_MEASUREMENT_CAPACITY:
            raise GlobalIndicatorDefinitionError(
                'Global indicator requires two or three measurements'
            )
        keys = [item.key for item in self.measurements]
        if len(keys) != len(set(keys)):
            raise GlobalIndicatorDefinitionError(
                'Global indicator contains duplicate measurement keys'
            )
        if self.last_measurement is not None and self.last_measurement.key in set(keys):
            raise GlobalIndicatorDefinitionError(
                'Global indicator last measurement key must be unique'
            )

    @classmethod
    def from_iterable(
        cls,
        *,
        key: str,
        label: str,
        unit: str,
        measurements: Iterable[GlobalIndicatorMeasurementState],
        last_measurement: GlobalIndicatorLastMeasurementState | None = None,
        definition_key: str | None = None,
        style: GlobalIndicatorStyle | None = None,
    ) -> GlobalIndicatorState:
        return cls(
            key=key,
            label=label,
            unit=unit,
            measurements=tuple(measurements),
            last_measurement=last_measurement,
            definition_key=definition_key,
            style=style or GlobalIndicatorStyle(),
        )

    @property
    def measurement_keys(self) -> tuple[str, ...]:
        return tuple(item.key for item in self.measurements)

    @property
    def all_measurement_keys(self) -> tuple[str, ...]:
        if self.last_measurement is None:
            return self.measurement_keys
        return (*self.measurement_keys, self.last_measurement.key)

    def to_component(self) -> Component:
        from .presentation import build_global_indicator

        return build_global_indicator(state=self)


@dataclass(frozen=True, slots=True)
class GlobalIndicatorCollection:
    indicators: tuple[GlobalIndicatorState, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, 'indicators', tuple(self.indicators))
        keys = [indicator.key for indicator in self.indicators]
        if len(keys) != len(set(keys)):
            raise GlobalIndicatorDefinitionError(
                'Global indicator collection contains duplicate keys'
            )

    @classmethod
    def from_iterable(
        cls,
        indicators: Iterable[GlobalIndicatorState],
    ) -> GlobalIndicatorCollection:
        return cls(indicators=tuple(indicators))

    def to_component(self) -> Component:
        from .presentation import build_global_indicators

        return build_global_indicators(collection=self)

    def __iter__(self) -> Iterator[GlobalIndicatorState]:
        return iter(self.indicators)

    def __len__(self) -> int:
        return len(self.indicators)


def global_indicator_measurement_capacity() -> int:
    return _GLOBAL_INDICATOR_MEASUREMENT_CAPACITY


def _require_key(value: str, *, field_name: str) -> None:
    if not _KEY_PATTERN.fullmatch(value):
        raise GlobalIndicatorDefinitionError(f'Invalid global indicator {field_name}: {value!r}')


def _require_text(value: str | None, *, field_name: str) -> None:
    if value is None or not value.strip():
        raise GlobalIndicatorDefinitionError(f'Global indicator {field_name} cannot be empty')


def _require_class_tokens(value: str, *, field_name: str) -> None:
    tokens = value.split()
    if not tokens or not all(_CLASS_TOKEN.fullmatch(token) for token in tokens):
        raise GlobalIndicatorDefinitionError(
            f'Invalid global indicator CSS classes for {field_name}: {value!r}'
        )
