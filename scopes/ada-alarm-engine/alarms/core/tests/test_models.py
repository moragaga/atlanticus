import pytest

from ada.alarms.core import (
    AlarmResolutionKey,
    AlarmRouting,
    DeactivationPolicy,
    PlannedAlarm,
    RoutingDestination,
)
from ada.contracts.alarms import AlarmIdentity, AlarmKind, Criticality


def test_resolution_key_requires_both_revisions() -> None:
    key = AlarmResolutionKey('ALARMS-1', 'TOOLS-1')
    assert key.alarm_configuration_revision == 'ALARMS-1'
    assert key.confirmed_tool_catalog_revision == 'TOOLS-1'

    with pytest.raises(ValueError, match='must not be empty'):
        AlarmResolutionKey('', 'TOOLS-1')


def test_c2_planned_alarm_requires_delayed_destinations() -> None:
    with pytest.raises(ValueError, match='require delay_seconds'):
        PlannedAlarm(
            identity=AlarmIdentity('mill', 'risk'),
            kind=AlarmKind.RISK,
            criticality=Criticality.C2,
            priority_group='mill-feed',
            priority_order=1,
            evaluator_key='threshold',
            alarm_configuration_revision='ALARMS-1',
            tool_registry_revision='TOOLS-1',
            routing=AlarmRouting(
                origin_tool_key='process',
                destinations=(RoutingDestination('io'),),
            ),
        )


def test_planned_alarm_preserves_execution_contract() -> None:
    plan = PlannedAlarm(
        identity=AlarmIdentity('mill', 'risk'),
        kind=AlarmKind.RISK,
        criticality=Criticality.C2,
        priority_group='mill-feed',
        priority_order=1,
        evaluator_key='threshold',
        alarm_configuration_revision='ALARMS-1',
        tool_registry_revision='TOOLS-1',
        routing=AlarmRouting(
            origin_tool_key='process',
            destinations=(RoutingDestination('io', 600),),
        ),
        deactivation_policy=DeactivationPolicy(approval_required=True),
        reappearance_after_seconds=900,
    )
    assert plan.routing.destinations[0].delay_seconds == 600
    assert plan.reappearance_after_seconds == 900
