# Mapea el contrato textual del backend a semántica visual sin convertirlo a número.
from __future__ import annotations

from enum import StrEnum


class DashboardValueStatus(StrEnum):
    NEUTRAL = 'neutral'
    DANGER = 'danger'
    WARNING = 'warning'


def map_dashboard_value_status(value: object) -> DashboardValueStatus:
    # "0" y null son estado normal; "1" y "2" expresan severidad semántica.
    if value is None or value == '0':
        return DashboardValueStatus.NEUTRAL
    if value == '1':
        return DashboardValueStatus.DANGER
    if value == '2':
        return DashboardValueStatus.WARNING
    raise ValueError('Dashboard value status must be "0", "1", "2" or null')
