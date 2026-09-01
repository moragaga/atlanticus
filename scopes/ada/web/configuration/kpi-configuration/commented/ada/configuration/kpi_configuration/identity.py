# Normaliza kpi_key y claves de destino sin crear identidades paralelas.
from ada.configuration.kpi_configuration.errors import KpiConfigurationValidationError


def require_kpi_key(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KpiConfigurationValidationError('KPI key must be a non-empty string')
    return value.strip()


def require_destination_key(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KpiConfigurationValidationError(
            'KPI destination key must be a non-empty string'
        )
    return value.strip()
