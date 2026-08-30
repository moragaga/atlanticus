from ada.configuration.tools.errors import ToolConfigurationValidationError
from ada.configuration.tools.models import ToolConfiguration

# Esta lista es política de la composición operacional ADA, no un catálogo global de Sources.
_SUPPORTED_ADA_CONTROL_SOURCE_KEYS = frozenset({'pi', 'dispatch'})


def validate_ada_operational_tool_sources(configuration: ToolConfiguration) -> None:
    # La validación de publicación aplica las reglas que Generic Application también protege en runtime.
    consumption = configuration.source_consumption
    participation = configuration.source_operational_participation
    # PI siempre debe estar declarada: no se inyecta mediante una regla oculta.
    if 'pi' not in consumption.source_keys:
        raise ToolConfigurationValidationError(
            "ADA operational Tool Configuration requires PI source consumption"
        )
    # Además de pertenecer a la Tool, PI debe controlar la degradación operacional.
    if not participation.controls('pi'):
        raise ToolConfigurationValidationError(
            'ADA operational Tool Configuration requires PI as a CONTROL source'
        )
    # En las Tools ADA actuales solo PI y Dispatch tienen semántica CONTROL.
    unsupported = tuple(
        source_key
        for source_key in participation.control_source_keys
        if source_key not in _SUPPORTED_ADA_CONTROL_SOURCE_KEYS
    )
    if unsupported:
        raise ToolConfigurationValidationError(
            'ADA operational Tool Configuration supports only PI and Dispatch as CONTROL '
            f'sources: {unsupported[0]!r}'
        )
    # Dispatch es opcional; cuando la Tool lo consume, debe participar como CONTROL.
    if 'dispatch' in consumption.source_keys and not participation.controls('dispatch'):
        raise ToolConfigurationValidationError(
            'Dispatch declared by Tool Source Consumption must participate as CONTROL'
        )
