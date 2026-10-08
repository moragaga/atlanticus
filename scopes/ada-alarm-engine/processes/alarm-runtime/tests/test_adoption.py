from dataclasses import replace

from ada.alarms.core import AlarmRouting, RoutingDestination
from ada.alarms.materialization import EngineAlarmConfiguration
from ada.contracts.alarms import AlarmKind, Criticality
from ada.processes.alarm_runtime import (
    ConfigurationAdoptionDisposition,
    ConfigurationAdoptionRejectionReason,
    plan_configuration_adoption,
)

from .support import engine_configuration


def _with_plan(
    configuration: EngineAlarmConfiguration,
    plan,
) -> EngineAlarmConfiguration:
    return EngineAlarmConfiguration(
        resolution_key=configuration.resolution_key,
        defined_alarm_identities=configuration.defined_alarm_identities,
        planned_alarms=(plan,),
        parameters_by_alarm=configuration.parameters_by_alarm,
    )


def test_parameter_evaluator_and_kind_changes_are_compatible() -> None:
    source = engine_configuration()
    parameter_target = engine_configuration(release='ALARMS-8', limit=12.0)
    evaluator_target = engine_configuration(release='ALARMS-8', evaluator_key='trend')
    kind_base = engine_configuration(release='ALARMS-8')
    kind_target = _with_plan(
        kind_base,
        replace(kind_base.planned_alarms[0], kind=AlarmKind.IMPACT),
    )

    for target in (parameter_target, evaluator_target, kind_target):
        plan = plan_configuration_adoption(source, target)
        assert plan.is_adoptable is True
        assert plan.changes[0].disposition is ConfigurationAdoptionDisposition.COMPATIBLE


def test_special_condition_flag_change_is_compatible() -> None:
    source = engine_configuration()
    target_base = engine_configuration(release='ALARMS-8')
    target = _with_plan(
        target_base,
        replace(target_base.planned_alarms[0], is_special_condition=True),
    )

    plan = plan_configuration_adoption(source, target)

    assert plan.is_adoptable is True
    assert plan.changes[0].disposition is ConfigurationAdoptionDisposition.COMPATIBLE


def test_disabled_and_removed_are_distinct_adoption_changes() -> None:
    source = engine_configuration()
    target_base = engine_configuration(release='ALARMS-8')
    identity = source.planned_alarms[0].identity
    disabled = EngineAlarmConfiguration(
        resolution_key=target_base.resolution_key,
        defined_alarm_identities=(identity,),
        planned_alarms=(),
        parameters_by_alarm={},
    )
    removed = EngineAlarmConfiguration(
        resolution_key=target_base.resolution_key,
        defined_alarm_identities=(),
        planned_alarms=(),
        parameters_by_alarm={},
    )

    assert plan_configuration_adoption(source, disabled).changes[0].disposition is (
        ConfigurationAdoptionDisposition.DISABLED
    )
    assert plan_configuration_adoption(source, removed).changes[0].disposition is (
        ConfigurationAdoptionDisposition.REMOVED
    )


def test_criticality_and_origin_changes_require_structural_reset() -> None:
    source = engine_configuration()
    target_base = engine_configuration(release='ALARMS-8')
    criticality_target = _with_plan(
        target_base,
        replace(target_base.planned_alarms[0], criticality=Criticality.C2),
    )
    origin_target = _with_plan(
        target_base,
        replace(
            target_base.planned_alarms[0],
            routing=AlarmRouting(origin_tool_key='tool_b'),
        ),
    )

    for target in (criticality_target, origin_target):
        plan = plan_configuration_adoption(source, target)
        assert plan.is_adoptable is True
        assert plan.changes[0].disposition is ConfigurationAdoptionDisposition.STRUCTURAL_RESET


def test_c2_destination_change_is_compatible() -> None:
    source_base = engine_configuration()
    source = _with_plan(
        source_base,
        replace(
            source_base.planned_alarms[0],
            criticality=Criticality.C2,
            routing=AlarmRouting(
                origin_tool_key='tool_a',
                destinations=(RoutingDestination(tool_key='tool_b', delay_seconds=300),),
            ),
        ),
    )
    target_base = engine_configuration(release='ALARMS-8')
    target = _with_plan(
        target_base,
        replace(
            target_base.planned_alarms[0],
            criticality=Criticality.C2,
            routing=AlarmRouting(
                origin_tool_key='tool_a',
                destinations=(RoutingDestination(tool_key='tool_b', delay_seconds=600),),
            ),
        ),
    )

    plan = plan_configuration_adoption(source, target)

    assert plan.is_adoptable is True
    assert plan.changes[0].disposition is ConfigurationAdoptionDisposition.COMPATIBLE


def test_priority_order_change_is_compatible_within_same_group() -> None:
    source = engine_configuration()
    target_base = engine_configuration(release='ALARMS-8')
    target = _with_plan(
        target_base,
        replace(target_base.planned_alarms[0], priority_order=2),
    )

    plan = plan_configuration_adoption(source, target)

    assert plan.is_adoptable is True
    assert plan.changes[0].disposition is ConfigurationAdoptionDisposition.COMPATIBLE
    assert plan.changes[0].rejection_reason is None


def test_priority_group_change_is_rejected_because_group_is_immutable() -> None:
    source = engine_configuration()
    target_base = engine_configuration(release='ALARMS-8')
    target = _with_plan(
        target_base,
        replace(target_base.planned_alarms[0], priority_group='other_group'),
    )

    plan = plan_configuration_adoption(source, target)

    assert plan.is_adoptable is False
    assert plan.changes[0].disposition is ConfigurationAdoptionDisposition.REJECTED
    assert plan.changes[0].rejection_reason is (
        ConfigurationAdoptionRejectionReason.PRIORITY_GROUP_IMMUTABLE
    )
