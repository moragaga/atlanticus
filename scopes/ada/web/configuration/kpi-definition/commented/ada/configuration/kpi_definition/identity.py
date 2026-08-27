from ada.configuration.kpi_definition.errors import KpiDefinitionValidationError


# La identidad se comparte semánticamente con otros dominios mediante kpi_key,
# pero este módulo no consulta ni depende de KPI Configuration.
def require_kpi_key(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KpiDefinitionValidationError('KPI key must be a non-empty string')
    return value.strip()


# Los nombres de metadata son abiertos para no congelar hoy las futuras columnas.
def require_field_name(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KpiDefinitionValidationError('KPI definition field name must be a non-empty string')
    return value.strip()
