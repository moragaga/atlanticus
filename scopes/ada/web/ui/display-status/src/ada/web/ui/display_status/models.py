from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .module import ADA_DISPLAY_STATUS_ASSET_LAYER


class DisplayStatus(StrEnum):
    OK = 'ok'
    NOT_MAPPED = 'not_mapped'
    EMPTY = 'empty'
    INVALID = 'invalid'
    ERROR = 'error'


@dataclass(frozen=True, slots=True)
class DisplayValue:
    status: DisplayStatus
    value: object | None = None

    def __post_init__(self) -> None:
        if self.status is DisplayStatus.OK and self.value is None:
            raise ValueError('OK display value requires a concrete value')
        if self.status is not DisplayStatus.OK and self.value is not None:
            raise ValueError('Degraded display value cannot expose a value')

    @classmethod
    def ok(cls, value: object) -> DisplayValue:
        return cls(DisplayStatus.OK, value)

    @classmethod
    def not_mapped(cls) -> DisplayValue:
        return cls(DisplayStatus.NOT_MAPPED)

    @classmethod
    def empty(cls) -> DisplayValue:
        return cls(DisplayStatus.EMPTY)

    @classmethod
    def invalid(cls) -> DisplayValue:
        return cls(DisplayStatus.INVALID)

    @classmethod
    def error(cls) -> DisplayValue:
        return cls(DisplayStatus.ERROR)


@dataclass(frozen=True, slots=True)
class StatusVisual:
    asset_name: str
    alt: str
    title: str

    @property
    def asset_url(self) -> str:
        return f'/assets/{ADA_DISPLAY_STATUS_ASSET_LAYER.target_name}/img/status/{self.asset_name}'


_STATUS_VISUALS = {
    DisplayStatus.NOT_MAPPED: StatusVisual(
        asset_name='not-mapped.svg',
        alt='Dato no mapeado',
        title='Dato no mapeado',
    ),
    DisplayStatus.EMPTY: StatusVisual(
        asset_name='empty-data.svg',
        alt='Sin datos',
        title='Sin datos',
    ),
    DisplayStatus.INVALID: StatusVisual(
        asset_name='invalid-data.svg',
        alt='Dato inválido',
        title='Dato inválido',
    ),
    DisplayStatus.ERROR: StatusVisual(
        asset_name='internal-error.svg',
        alt='Error interno',
        title='Error interno',
    ),
}


def resolve_status_visual(status: DisplayStatus) -> StatusVisual | None:
    return _STATUS_VISUALS.get(status)


def coerce_display_value(value: Any, *, present: bool = True) -> DisplayValue:
    if isinstance(value, DisplayValue):
        return value
    if not present:
        return DisplayValue.not_mapped()
    if value is None:
        return DisplayValue.empty()

    status = _read_status(value)
    if status is None:
        return DisplayValue.ok(value)

    payload = _read_value(value)
    if status is DisplayStatus.OK:
        if payload is None:
            return DisplayValue.invalid()
        return DisplayValue.ok(payload)
    return DisplayValue(status)


def _read_status(value: Any) -> DisplayStatus | None:
    raw_status: Any
    if isinstance(value, dict):
        if 'status' not in value:
            return None
        raw_status = value.get('status')
    elif hasattr(value, 'status'):
        raw_status = value.status
    else:
        return None

    if isinstance(raw_status, StrEnum):
        raw_status = raw_status.value
    if not isinstance(raw_status, str):
        return DisplayStatus.ERROR
    try:
        return DisplayStatus(raw_status)
    except ValueError:
        return DisplayStatus.ERROR


def _read_value(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get('value')
    return getattr(value, 'value', None)
