from ada.configuration.kpi_definition.errors import KpiDefinitionValidationError


def require_kpi_key(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KpiDefinitionValidationError('KPI key must be a non-empty string')
    return value.strip()


def require_field_name(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KpiDefinitionValidationError('KPI definition field name must be a non-empty string')
    return value.strip()
