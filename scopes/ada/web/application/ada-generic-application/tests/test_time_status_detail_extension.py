from __future__ import annotations

from ada.contracts.tools.sources import SourceControlPolicy, ToolSourceConsumption, ToolSourceOperationalParticipation
from ada.web.application.generic.application import create_application_definition
from ada.web.application.generic.extension import AdaApplicationExtension
from ada.web.time_status.runtime import TimeStatusDetailProvider
from ada.web.ui.time_status import TimeStatusDetailSourceState, TimeStatusDetailState


def test_extension_provider_can_be_bound_to_existing_consumed_sources() -> None:
    provider = TimeStatusDetailProvider(
        source_keys=('blockgrade',),
        resolve=lambda _store: TimeStatusDetailState((
            TimeStatusDetailSourceState('blockgrade', 'BlockGrade', 'Sin información'),
        )),
    )
    extension = AdaApplicationExtension(time_status_detail=provider)
    definition = create_application_definition(
        source_consumption=ToolSourceConsumption('process', ('pi', 'blockgrade')),
        source_operational_participation=ToolSourceOperationalParticipation(
            'process',
            control_sources=(SourceControlPolicy('pi', 200, 300),),
            additional_observation_source_keys=('blockgrade',),
        ),
        time_status_detail=extension.time_status_detail,
    )
    runtime_binding = definition.layout.keywords['time_status_binding']
    assert runtime_binding.detail is provider
