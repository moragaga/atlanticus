from dataclasses import replace

import pytest

from ada.web.tools.enums import ToolConfigurationKind
from ada_command_center.alarms.materialization import (
    DeliveryAlarmConfiguration,
    ResolvedDeactivationPolicy,
    ResolvedDeliveryMessage,
    ResolvedVisualSubcomponentTarget,
    ResolvedVisualTarget,
)
from ada_command_center.domain.alarms import ProcessAlarmProjectionMode, VisibilityMode

from .support import delivery_alarm, resolution_key


def test_resolved_deactivation_policy_preserves_enabled_contract() -> None:
    policy = ResolvedDeactivationPolicy(
        enabled=True,
        max_duration_hours=4,
        approval_required=True,
    )
    assert policy.max_duration_hours == 4
    with pytest.raises(ValueError, match='requires max_duration_hours'):
        ResolvedDeactivationPolicy(
            enabled=True,
            max_duration_hours=None,
            approval_required=False,
        )
    with pytest.raises(ValueError, match='must not require approval'):
        ResolvedDeactivationPolicy(
            enabled=False,
            max_duration_hours=None,
            approval_required=True,
        )


def test_resolved_delivery_message_requires_effective_policy() -> None:
    policy = ResolvedDeactivationPolicy(
        enabled=False,
        max_duration_hours=None,
        approval_required=False,
    )
    message = ResolvedDeliveryMessage(
        message_key='normal-operation',
        display_text='Normal operation',
        deactivation_policy=policy,
    )
    assert message.deactivation_policy is policy


def test_resolved_visual_target_uses_stable_resolved_references() -> None:
    target = ResolvedVisualTarget(
        tool_key='process-sag',
        tool_kind=ToolConfigurationKind.PROCESS,
        component_keys=('feed',),
        subcomponents=(
            ResolvedVisualSubcomponentTarget(
                owner_component_key='feed',
                subcomponent_key='rate',
            ),
        ),
        process_projection_mode=ProcessAlarmProjectionMode.DISTRIBUTED,
    )
    assert target.tool_key == 'process-sag'
    with pytest.raises(ValueError, match='component_keys'):
        ResolvedVisualTarget(
            tool_key='process-sag',
            tool_kind=ToolConfigurationKind.PROCESS,
            component_keys=('feed', 'feed'),
        )


def test_delivery_configuration_rejects_duplicate_alarm_identities() -> None:
    alarm = delivery_alarm()
    with pytest.raises(ValueError, match='duplicate alarm identities'):
        DeliveryAlarmConfiguration(
            resolution_key=resolution_key(),
            alarms=(alarm, alarm),
        )


def test_delivery_represents_disabled_trace_only_rule_without_removing_it() -> None:
    alarm = replace(
        delivery_alarm(),
        is_active=False,
        visibility_mode=VisibilityMode.TRACE_ONLY,
    )
    configuration = DeliveryAlarmConfiguration(
        resolution_key=resolution_key(),
        alarms=(alarm,),
    )
    assert configuration.alarms == (alarm,)
