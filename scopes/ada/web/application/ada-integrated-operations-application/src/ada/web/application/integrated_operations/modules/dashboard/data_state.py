from __future__ import annotations

from enum import StrEnum


class DashboardDataState(StrEnum):
    OK = 'ok'
    UNSHIFT = 'unshift'
    ERROR = 'error'


def map_dashboard_data_state(value: object) -> DashboardDataState:
    if not isinstance(value, str):
        raise ValueError('Dashboard data_state must be ok, unshift or error')
    try:
        return DashboardDataState(value)
    except ValueError as error:
        raise ValueError('Dashboard data_state must be ok, unshift or error') from error
