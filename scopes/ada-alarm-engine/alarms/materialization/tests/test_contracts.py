from dataclasses import replace

import pytest

from ada.alarms.materialization import (
    DeliveryAlarmConfiguration,
    EngineAlarmConfiguration,
    ModelerAlarmConfiguration,
    ResolvedDeactivationPolicy,
    ResolvedModelerMessage,
)
from ada.contracts.alarms import VisibilityMode

from .support import identity, modeler_alarm, plan, resolution_key


def test_engine_configuration_distinguishes_defined_and_executable_alarms() -> None:
    active = plan()
    disabled = identity('disabled')
    configuration = EngineAlarmConfiguration(
        resolution_key=resolution_key(),
        defined_alarm_identities=(active.identity, disabled),
        planned_alarms=(active,),
        parameters_by_alarm={active.identity: {'limit': 10.0}},
    )
    assert disabled in configuration.defined_alarm_identities
    assert tuple(alarm.identity for alarm in configuration.planned_alarms) == (active.identity,)
    assert disabled not in configuration.parameters_by_alarm


def test_modeler_configuration_preserves_projection_metadata_for_disabled_rule() -> None:
    alarm = replace(
        modeler_alarm(),
        is_active=False,
        visibility_mode=VisibilityMode.TRACE_ONLY,
    )
    configuration = ModelerAlarmConfiguration(
        resolution_key=resolution_key(),
        alarms=(alarm,),
    )
    assert configuration.alarms[0].priority_group == 'mill-feed'
    assert configuration.alarms[0].priority_order == 1
    assert configuration.alarms[0].is_active is False


def test_resolved_modeler_message_carries_effective_deactivation_policy() -> None:
    policy = ResolvedDeactivationPolicy(
        enabled=False,
        max_duration_hours=None,
        approval_required=False,
    )
    message = ResolvedModelerMessage(
        message_key='normal-operation',
        display_text='Normal operation',
        deactivation_policy=policy,
    )
    assert message.deactivation_policy is policy


def test_delivery_configuration_is_only_logical_publication_inventory() -> None:
    configuration = DeliveryAlarmConfiguration(
        resolution_key=resolution_key(),
        publication_tool_keys=('tool-b', 'tool-a'),
    )
    assert configuration.publication_tool_keys == ('tool-a', 'tool-b')

    with pytest.raises(ValueError, match='duplicates'):
        DeliveryAlarmConfiguration(
            resolution_key=resolution_key(),
            publication_tool_keys=('tool-a', 'tool-a'),
        )
