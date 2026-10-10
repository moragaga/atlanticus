from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

_LATEST_ENTRY_FIELDS = frozenset({'status', 'value_kind', 'value_type', 'value', 'parsed_value'})
_VALUE_KINDS = frozenset({'value', 'json'})
_VALUE_TYPES = frozenset({'text', 'integer', 'float', 'boolean'})


class KpiLatestValueState(StrEnum):
    OK = 'ok'
    NOT_MAPPED = 'not_mapped'
    MISSING = 'missing'
    INVALID = 'invalid'
    ERROR = 'error'


@dataclass(frozen=True, slots=True)
class DecodedKpiLatestValue:
    state: KpiLatestValueState
    value_kind: str | None = None
    value: object | None = None
    value_type: str | None = None
    parsed_value: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, KpiLatestValueState):
            raise TypeError('state must be KpiLatestValueState')
        if self.state is KpiLatestValueState.OK:
            if self.value_kind not in _VALUE_KINDS:
                raise ValueError('OK latest value requires a supported value_kind')
            if self.value_kind == 'json':
                if (
                    not isinstance(self.value, list | dict)
                    or self.value_type is not None
                    or self.parsed_value is not None
                ):
                    raise TypeError(
                        'JSON latest value requires a JSON payload without scalar metadata'
                    )
            elif (
                self.value_type not in _VALUE_TYPES
                or not isinstance(self.value, str)
                or not isinstance(self.parsed_value, str)
            ):
                raise TypeError('VALUE latest requires a value_type and two string representations')
            return
        if self.value is not None or self.parsed_value is not None:
            raise ValueError('Degraded latest value cannot expose a value')
        if self.state is KpiLatestValueState.MISSING and self.value_kind not in {None, 'json'}:
            raise ValueError('MISSING latest value kind must be omitted or json')
        if self.value_kind is not None and self.value_kind not in _VALUE_KINDS:
            raise ValueError('Degraded latest value contains an unsupported value_kind')
        if self.value_kind == 'json' and self.value_type is not None:
            raise ValueError('Degraded JSON latest value cannot declare value_type')
        if self.value_kind == 'value' and self.value_type not in _VALUE_TYPES:
            raise ValueError('Degraded VALUE latest requires value_type')
        if self.value_kind is None and self.value_type is not None:
            raise ValueError('Degraded latest without kind cannot declare value_type')


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
    parsed = value['parsed_value']
    value_type = value['value_type']
    if value_kind == 'json':
        if value_type is not None or parsed is not None:
            return DecodedKpiLatestValue(KpiLatestValueState.INVALID)
        if status == 'ok' and not isinstance(payload, list | dict):
            return DecodedKpiLatestValue(KpiLatestValueState.INVALID)
    elif value_kind == 'value':
        if value_type not in _VALUE_TYPES:
            return DecodedKpiLatestValue(KpiLatestValueState.INVALID)
        if status == 'ok' and (not isinstance(payload, str) or not isinstance(parsed, str)):
            return DecodedKpiLatestValue(KpiLatestValueState.INVALID)
    elif value_type is not None or parsed is not None:
        return DecodedKpiLatestValue(KpiLatestValueState.INVALID)
    if status == 'ok':
        if value_kind not in _VALUE_KINDS:
            return DecodedKpiLatestValue(KpiLatestValueState.INVALID)
        return DecodedKpiLatestValue(
            KpiLatestValueState.OK,
            value_kind=value_kind,
            value=payload,
            value_type=value_type,
            parsed_value=parsed,
        )
    if status == 'missing':
        if value_kind not in {None, 'json'} or payload is not None:
            return DecodedKpiLatestValue(KpiLatestValueState.INVALID)
        return DecodedKpiLatestValue(KpiLatestValueState.MISSING, value_kind=value_kind)
    if status == 'error':
        if payload is not None or value_kind not in _VALUE_KINDS:
            return DecodedKpiLatestValue(KpiLatestValueState.INVALID)
        return DecodedKpiLatestValue(
            KpiLatestValueState.ERROR, value_kind=value_kind, value_type=value_type
        )
    return DecodedKpiLatestValue(KpiLatestValueState.INVALID)
