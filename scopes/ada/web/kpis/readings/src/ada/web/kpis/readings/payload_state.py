from __future__ import annotations

from enum import StrEnum


class KpiPayloadDataState(StrEnum):
    OK = 'ok'
    UNSHIFT = 'unshift'
    ERROR = 'error'


def map_kpi_payload_data_state(value: object) -> KpiPayloadDataState:
    if not isinstance(value, str):
        raise ValueError('KPI payload data_state must be ok, unshift or error')
    try:
        return KpiPayloadDataState(value)
    except ValueError as error:
        raise ValueError('KPI payload data_state must be ok, unshift or error') from error
