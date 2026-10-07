from __future__ import annotations

from enum import StrEnum


class DashboardValueStatus(StrEnum):
    NEUTRAL = 'neutral'
    DANGER = 'danger'
    WARNING = 'warning'


def map_dashboard_value_status(value: object) -> DashboardValueStatus:
    if value is None or value == '0':
        return DashboardValueStatus.NEUTRAL
    if value == '1':
        return DashboardValueStatus.DANGER
    if value == '2':
        return DashboardValueStatus.WARNING
    raise ValueError('Dashboard value status must be "0", "1", "2" or null')
