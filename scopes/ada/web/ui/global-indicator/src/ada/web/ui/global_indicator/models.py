from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Literal, TypeAlias

from dash.development.base_component import Component

from ada.web.ui.display_status import DisplayValue, coerce_display_value

from .errors import GlobalIndicatorDefinitionError

_KEY_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')
_GLOBAL_INDICATOR_MEASUREMENT_CAPACITY = 3
_GLOBAL_INDICATOR_TEXT_SCALES = frozenset({'prominent', 'standard', 'compact', 'micro'})

IndicatorPrimitive: TypeAlias = str | int | float | Component
IndicatorInput: TypeAlias = IndicatorPrimitive | DisplayValue | None
IndicatorColorClass: TypeAlias = str | Component | None
GlobalIndicatorTextScale: TypeAlias = Literal['prominent', 'standard', 'compact', 'micro']


@dataclass(frozen=True, slots=True)
class GlobalIndicatorStyle:
    heading_scale: GlobalIndicatorTextScale = 'compact'
    measurement_label_scale: GlobalIndicatorTextScale = 'standard'
    actual_value_scale: GlobalIndicatorTextScale = 'prominent'
    plan_value_scale: GlobalIndicatorTextScale = 'standard'
    last_measurement_label_scale: GlobalIndicatorTextScale = 'micro'
    last_measurement_value_scale: GlobalIndicatorTextScale = 'compact'

    def __post_init__(self) -> None:
        for field_name in (
            'heading_scale',
            'measurement_label_scale',
            'actual_value_scale',
            'plan_value_scale',
            'last_measurement_label_scale',
            'last_measurement_value_scale',
        ):
            _require_text_scale(getattr(self, field_name), field_name=field_name)


@dataclass(frozen=True, slots=True)
class GlobalIndicatorMeasurementState:
    key: str
    label: str
    actual_value: IndicatorInput
    plan_value: IndicatorInput
    color_class: IndicatorColorClass = None
    actual_kpi_key: str | None = None
    plan_kpi_key: str | None = None

    def __post_init__(self) -> None:
        _require_key(self.key, field_name='measurement key')
        _require_text(self.label, field_name='measurement label')
        object.__setattr__(self, 'actual_value', coerce_display_value(self.actual_value))
        object.__setattr__(self, 'plan_value', coerce_display_value(self.plan_value))
        if self.actual_kpi_key is not None:
            object.__setattr__(
                self,
                'actual_kpi_key',
                _require_kpi_key(self.actual_kpi_key, field_name='actual_kpi_key'),
            )
        if self.plan_kpi_key is not None:
            object.__setattr__(
                self,
                'plan_kpi_key',
                _require_kpi_key(self.plan_kpi_key, field_name='plan_kpi_key'),
            )


@dataclass(frozen=True, slots=True)
class GlobalIndicatorLastMeasurementState:
    actual_value: IndicatorInput
    key: str = 'latest'
    label: str = 'Última medición'
    color_class: IndicatorColorClass = None
    actual_kpi_key: str | None = None

    def __post_init__(self) -> None:
        _require_key(self.key, field_name='last measurement key')
        _require_text(self.label, field_name='last measurement label')
        object.__setattr__(self, 'actual_value', coerce_display_value(self.actual_value))
        if self.actual_kpi_key is not None:
            object.__setattr__(
                self,
                'actual_kpi_key',
                _require_kpi_key(self.actual_kpi_key, field_name='actual_kpi_key'),
            )


@dataclass(frozen=True, slots=True)
class GlobalIndicatorState:
    key: str
    label: str
    unit: str
    measurements: tuple[GlobalIndicatorMeasurementState, ...]
    last_measurement: GlobalIndicatorLastMeasurementState | None = None
    style: GlobalIndicatorStyle = field(default_factory=GlobalIndicatorStyle)

    def __post_init__(self) -> None:
        object.__setattr__(self, 'measurements', tuple(self.measurements))
        _require_key(self.key, field_name='key')
        _require_text(self.label, field_name='label')
        _require_text(self.unit, field_name='unit')
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
        style: GlobalIndicatorStyle | None = None,
    ) -> GlobalIndicatorState:
        return cls(
            key=key,
            label=label,
            unit=unit,
            measurements=tuple(measurements),
            last_measurement=last_measurement,
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


def _require_kpi_key(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise GlobalIndicatorDefinitionError(f'Global indicator {field_name} cannot be empty')
    return normalized


def _require_text(value: str | None, *, field_name: str) -> None:
    if value is None or not value.strip():
        raise GlobalIndicatorDefinitionError(f'Global indicator {field_name} cannot be empty')


def _require_text_scale(value: str, *, field_name: str) -> None:
    if value not in _GLOBAL_INDICATOR_TEXT_SCALES:
        raise GlobalIndicatorDefinitionError(
            f'Invalid global indicator text scale for {field_name}: {value!r}'
        )
