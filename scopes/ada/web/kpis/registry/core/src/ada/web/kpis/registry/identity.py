from ada.web.kpis.registry.errors import KpiRegistryValidationError


def require_kpi_key(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KpiRegistryValidationError('KPI key must be a non-empty string')
    return value.strip()


def require_destination_key(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KpiRegistryValidationError('KPI destination key must be a non-empty string')
    return value.strip()
