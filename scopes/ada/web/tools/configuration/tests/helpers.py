from __future__ import annotations

from ada.web.tools.configuration import ToolConfiguration
from ada.web.tools.enums import (
    ProcessLayoutRole,
    ToolConfigurationKind,
    ToolScope,
)
from ada.web.tools.sources import (
    SourceControlPolicy,
    ToolSourceConsumption,
    ToolSourceOperationalParticipation,
)
from ada.web.tools.structure import (
    ToolComponent,
    ToolStructure,
    ToolSubcomponent,
)


def valid_configuration() -> ToolConfiguration:
    return ToolConfiguration(
        tool_key='process',
        display_name='Process',
        kind=ToolConfigurationKind.PROCESS,
        source_consumption=ToolSourceConsumption(
            tool_key='process',
            source_keys=('pi', 'blockgrade'),
        ),
        source_operational_participation=ToolSourceOperationalParticipation(
            tool_key='process',
            control_sources=(SourceControlPolicy('pi', 200, 300),),
            additional_observation_source_keys=('blockgrade',),
        ),
        structure=ToolStructure(
            tool_key='process',
            kind=ToolConfigurationKind.PROCESS,
            operational_scope=ToolScope.MINE,
            components=(
                ToolComponent(
                    key='mina',
                    display_name='Mina',
                    layout_role=ProcessLayoutRole.CENTER,
                    subcomponents=(ToolSubcomponent(key='carguio', display_name='Carguío'),),
                ),
            ),
        ),
    )


def configuration_without_structure() -> ToolConfiguration:
    base = valid_configuration()
    return ToolConfiguration(
        tool_key=base.tool_key,
        display_name=base.display_name,
        kind=base.kind,
        source_consumption=base.source_consumption,
        source_operational_participation=base.source_operational_participation,
        structure=None,
    )
