# Decoder canónico del envelope Latest de KPI Delivery. Esta capa traduce el contrato de transporte
# a un estado semántico reutilizable, pero deliberadamente no conoce Dash ni decide cómo presentar
# errores o datos ausentes. Cada consumidor mantiene esa responsabilidad.

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

_LATEST_ENTRY_FIELDS = frozenset({'status', 'value_kind', 'value'})
_VALUE_KINDS = frozenset({'value', 'json'})


class KpiLatestValueState(StrEnum):
    OK = 'ok'
    NOT_MAPPED = 'not_mapped'
    MISSING = 'missing'
    INVALID = 'invalid'
    ERROR = 'error'


# El valor concreto solo existe en estado OK. Un error puede conservar value_kind porque Delivery
# permite conocer el tipo esperado aun cuando no haya payload, pero nunca conserva value.
@dataclass(frozen=True, slots=True)
class DecodedKpiLatestValue:
    state: KpiLatestValueState
    value_kind: str | None = None
    value: object | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, KpiLatestValueState):
            raise TypeError('state must be KpiLatestValueState')
        if self.state is KpiLatestValueState.OK:
            if self.value_kind not in _VALUE_KINDS:
                raise ValueError('OK latest value requires a supported value_kind')
            if self.value is None:
                raise ValueError('OK latest value requires a concrete value')
            if self.value_kind == 'json' and not isinstance(self.value, list | dict):
                raise TypeError('JSON latest value requires a list or dict')
            return
        if self.value is not None:
            raise ValueError('Degraded latest value cannot expose a value')
        if self.state is KpiLatestValueState.MISSING and self.value_kind is not None:
            raise ValueError('MISSING latest value cannot expose value_kind')
        if self.value_kind is not None and self.value_kind not in _VALUE_KINDS:
            raise ValueError('Degraded latest value contains an unsupported value_kind')


# present=False representa una clave que el destination no publicó y evita que cada consumidor
# invente su propia interpretación de NOT_MAPPED. Los envelopes presentes se validan exactamente.
def decode_kpi_latest_value(
    value: object,
    *,
    present: bool = True,
) -> DecodedKpiLatestValue:
    if not present:
        return DecodedKpiLatestValue(KpiLatestValueState.NOT_MAPPED)
    if not isinstance(value, Mapping) or set(value) != _LATEST_ENTRY_FIELDS:
        return DecodedKpiLatestValue(KpiLatestValueState.INVALID)

    status = value['status']
    value_kind = value['value_kind']
    payload = value['value']
    if status == 'ok':
        if value_kind not in _VALUE_KINDS or payload is None:
            return DecodedKpiLatestValue(KpiLatestValueState.INVALID)
        if value_kind == 'json' and not isinstance(payload, list | dict):
            return DecodedKpiLatestValue(KpiLatestValueState.INVALID)
        return DecodedKpiLatestValue(
            KpiLatestValueState.OK,
            value_kind=value_kind,
            value=payload,
        )
    if status == 'missing':
        if value_kind is not None or payload is not None:
            return DecodedKpiLatestValue(KpiLatestValueState.INVALID)
        return DecodedKpiLatestValue(KpiLatestValueState.MISSING)
    if status == 'error':
        if payload is not None or (value_kind is not None and value_kind not in _VALUE_KINDS):
            return DecodedKpiLatestValue(KpiLatestValueState.INVALID)
        return DecodedKpiLatestValue(KpiLatestValueState.ERROR, value_kind=value_kind)
    return DecodedKpiLatestValue(KpiLatestValueState.INVALID)
