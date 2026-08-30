from ada.configuration.tool_source_consumption import ToolSourceConsumption
from ada.configuration.tool_source_operational_participation.errors import (
    ToolSourceOperationalParticipationValidationError,
)
from ada.configuration.tool_source_operational_participation.models import (
    ToolSourceOperationalParticipation,
)


def validate_operational_participation_against_consumption(
    *,
    consumption: ToolSourceConsumption,
    participation: ToolSourceOperationalParticipation,
) -> None:
    if consumption.tool_key != participation.tool_key:
        raise ToolSourceOperationalParticipationValidationError(
            'Operational participation tool key must match source consumption tool key'
        )
    declared_source_keys = set(consumption.source_keys)
    for source_key in (
        participation.control_source_keys + participation.additional_observation_source_keys
    ):
        if source_key not in declared_source_keys:
            raise ToolSourceOperationalParticipationValidationError(
                f'Source is not declared by Tool Source Consumption: {source_key!r}'
            )
