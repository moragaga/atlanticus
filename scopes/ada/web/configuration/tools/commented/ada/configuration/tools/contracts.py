# Estas validaciones separan la validez de un draft de los requisitos necesarios para publicar una Tool operacional ADA.
from ada.configuration.tools.errors import ToolConfigurationValidationError
from ada.configuration.tools.models import ToolConfiguration

_SUPPORTED_ADA_CONTROL_SOURCE_KEYS = frozenset({'pi', 'dispatch'})


def validate_ada_operational_tool_sources(configuration: ToolConfiguration) -> None:
    consumption = configuration.source_consumption
    participation = configuration.source_operational_participation
    if 'pi' not in consumption.source_keys:
        raise ToolConfigurationValidationError(
            'ADA operational Tool Configuration requires PI source consumption'
        )
    if not participation.controls('pi'):
        raise ToolConfigurationValidationError(
            'ADA operational Tool Configuration requires PI as a CONTROL source'
        )
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
    if 'dispatch' in consumption.source_keys and not participation.controls('dispatch'):
        raise ToolConfigurationValidationError(
            'Dispatch declared by Tool Source Consumption must participate as CONTROL'
        )


def validate_ada_operational_tool_configuration(
    configuration: ToolConfiguration,
) -> None:
    validate_ada_operational_tool_sources(configuration)
    if configuration.structure is None:
        raise ToolConfigurationValidationError(
            'ADA operational Tool Configuration requires Tool Structure'
        )
