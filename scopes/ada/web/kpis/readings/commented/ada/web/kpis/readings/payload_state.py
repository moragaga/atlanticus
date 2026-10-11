from __future__ import annotations

from enum import StrEnum


# Estados operacionales declarados dentro del JSON de un KPI estructurado.
# No indican errores de transporte ni sustituyen DisplayStatus o ContentState.
class KpiPayloadDataState(StrEnum):
    OK = 'ok'
    UNSHIFT = 'unshift'
    ERROR = 'error'


def map_kpi_payload_data_state(value: object) -> KpiPayloadDataState:
    # Rechaza valores ausentes, numéricos y estados que no pertenezcan al contrato.
    if not isinstance(value, str):
        raise ValueError('KPI payload data_state must be ok, unshift or error')
    try:
        return KpiPayloadDataState(value)
    except ValueError as error:
        raise ValueError('KPI payload data_state must be ok, unshift or error') from error
