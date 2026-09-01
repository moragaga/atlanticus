# Snapshot inmutable que Delivery consume después de que la configuración administrativa fue validada.
# Delivery no administra Source/History/Workspace ni consulta Cosmos; sólo valida la frontera que necesita.

from __future__ import annotations

from dataclasses import dataclass

from ada.kpis.delivery.errors import KpiDeliveryValidationError


def _require_key(value: str, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f'{field_name} must be str')
    if not value or value != value.strip():
        raise KpiDeliveryValidationError(f'{field_name} must be a non-empty trimmed string')
    return value


@dataclass(frozen=True, slots=True)
class KpiDeliveryBinding:
    key: str
    destination_keys: tuple[str, ...]
    latest_enabled: bool
    series_enabled: bool
    series_hours: int | None = None

    def __post_init__(self) -> None:
        _require_key(self.key, field_name='binding key')
        if not isinstance(self.destination_keys, tuple):
            raise TypeError('destination_keys must be tuple')
        if not self.destination_keys:
            raise KpiDeliveryValidationError('destination_keys must contain at least one destination')
        destinations = tuple(
            _require_key(destination, field_name='destination key')
            for destination in self.destination_keys
        )
        if len(set(destinations)) != len(destinations):
            raise KpiDeliveryValidationError('destination_keys must not contain duplicates')
        if not isinstance(self.latest_enabled, bool):
            raise TypeError('latest_enabled must be bool')
        if not isinstance(self.series_enabled, bool):
            raise TypeError('series_enabled must be bool')
        if self.series_hours is not None:
            if isinstance(self.series_hours, bool) or not isinstance(self.series_hours, int):
                raise TypeError('series_hours must be int or None')
            if not 1 <= self.series_hours <= 24:
                raise KpiDeliveryValidationError('series_hours must be between 1 and 24')
        if self.series_enabled and self.series_hours is None:
            raise KpiDeliveryValidationError('series_hours is required when series_enabled is true')


@dataclass(frozen=True, slots=True)
class KpiDeliveryConfiguration:
    revision: str
    bindings: tuple[KpiDeliveryBinding, ...]
    tool_projection_revision: str | None = None

    def __post_init__(self) -> None:
        _require_key(self.revision, field_name='configuration revision')
        if self.tool_projection_revision is not None:
            _require_key(self.tool_projection_revision, field_name='tool projection revision')
        if not isinstance(self.bindings, tuple):
            raise TypeError('bindings must be tuple')
        if not all(isinstance(binding, KpiDeliveryBinding) for binding in self.bindings):
            raise TypeError('bindings must contain KpiDeliveryBinding values')
        keys = tuple(binding.key for binding in self.bindings)
        if len(set(keys)) != len(keys):
            raise KpiDeliveryValidationError('bindings must not contain duplicate KPI keys')
