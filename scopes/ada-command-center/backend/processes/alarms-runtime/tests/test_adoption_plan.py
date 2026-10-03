import pytest
from ada.contracts.alarms import AlarmIdentity, AlarmKind, Criticality

from ada_command_center.alarms.core import AlarmResolutionKey, AlarmRouting, PlannedAlarm
from ada_command_center.alarms.materialization import (
    AlarmConfigurationArtifactRef,
    DeliveryAlarmConfiguration,
    ReadyAlarmMaterialization,
    RuntimeAlarmConfiguration,
)
from ada_command_center.processes.alarms_runtime import (
    AlarmConfigurationRevision,
    AlarmConfigurationRevisionError,
    AlarmEvaluatorContract,
    AlarmEvaluatorRegistry,
    ConfigurationAdoptionChange,
    ConfigurationAdoptionDisposition,
    ConfigurationAdoptionPlan,
    ConfigurationAdoptionPlanError,
    ConfigurationAdoptionRejectionReason,
    build_alarm_configuration_revision,
    build_alarm_execution_session,
    plan_configuration_adoption,
)


def _identity(name):
    return AlarmIdentity(family_key='family', alarm_key=name)


def _registry(*names):
    return AlarmEvaluatorRegistry(
        contracts=tuple(
            AlarmEvaluatorContract(
                family_key='family',
                evaluator_key=name,
                evaluator=lambda context: None,
            )
            for name in names
        )
    )


def _plan(
    name,
    key,
    *,
    order=1,
    group='group-a',
    evaluator='threshold',
    kind=AlarmKind.RISK,
    criticality=Criticality.C3,
):
    return PlannedAlarm(
        identity=_identity(name),
        kind=kind,
        criticality=criticality,
        priority_group=group,
        priority_order=order,
        evaluator_key=evaluator,
        alarm_configuration_revision=key.alarm_configuration_revision,
        tool_registry_revision=key.confirmed_tool_catalog_revision,
        routing=AlarmRouting(origin_tool_key='tool-a'),
    )


def _ref(result_char, *, key=None, source_key='alarm-configuration', digest_char='f'):
    return AlarmConfigurationArtifactRef(
        source_key=source_key,
        result_id='alarm-materialization-' + result_char * 64,
        manifest_sha256=digest_char * 64,
        resolution_key=key or AlarmResolutionKey('R10', 'C5'),
    )


def _revision(
    result_char,
    *,
    defined=(),
    executable=(),
    key=None,
    order=1,
    source_key='alarm-configuration',
    evaluator='threshold',
    group='group-a',
    kind=AlarmKind.RISK,
    criticality=Criticality.C3,
):
    ref = _ref(result_char, key=key, source_key=source_key)
    session = build_alarm_execution_session(
        alarm_configuration_revision=ref.resolution_key.alarm_configuration_revision,
        tool_registry_revision=ref.resolution_key.confirmed_tool_catalog_revision,
        planned_alarms=tuple(
            _plan(
                name,
                ref.resolution_key,
                order=order,
                evaluator=evaluator,
                group=group,
                kind=kind,
                criticality=criticality,
            )
            for name in executable
        ),
        evaluator_registry=_registry('threshold', 'alternate'),
    )
    return AlarmConfigurationRevision(
        artifact_ref=ref,
        defined_alarm_identities=tuple(_identity(name) for name in defined),
        session=session,
    )


def _changes(plan):
    return {change.identity.alarm_key: change.disposition for change in plan.changes}


def test_same_resolution_key_with_different_result_ids_remains_plannable():
    source = _revision('a', defined=('active',), executable=('active',))
    target = _revision('b', defined=('active',), executable=('active',))
    plan = plan_configuration_adoption(source, target)
    assert source.revision_key == target.revision_key
    assert source.artifact_ref != target.artifact_ref
    assert _changes(plan) == {'active': ConfigurationAdoptionDisposition.UNCHANGED}
    assert plan.is_adoptable
    assert not plan.requires_execution_upgrade


def test_same_artifact_is_not_a_new_adoption():
    revision = _revision('a')
    with pytest.raises(ConfigurationAdoptionPlanError, match='must differ'):
        plan_configuration_adoption(revision, revision)


def test_same_result_id_with_other_manifest_digest_fails_closed():
    source = _revision('a')
    target = AlarmConfigurationRevision(
        artifact_ref=_ref('a', digest_char='e'),
        defined_alarm_identities=(),
        session=source.session,
    )
    with pytest.raises(ConfigurationAdoptionPlanError, match='conflicting'):
        plan_configuration_adoption(source, target)


def test_cross_source_adoption_is_rejected():
    source = _revision('a')
    target = _revision('b', source_key='different-source')
    with pytest.raises(ConfigurationAdoptionPlanError, match='source_key'):
        plan_configuration_adoption(source, target)


def test_union_includes_newly_added_active_disabled_and_reenabled_rules():
    source = _revision(
        'a',
        defined=('disabled', 'removed', 'retained', 're_enabled'),
        executable=('removed', 'retained'),
    )
    target = _revision(
        'b',
        defined=('added_active', 'added_disabled', 'disabled', 'retained', 're_enabled'),
        executable=('added_active', 're_enabled', 'retained'),
    )
    plan = plan_configuration_adoption(source, target)
    assert _changes(plan) == {
        'added_active': ConfigurationAdoptionDisposition.ADDED,
        'added_disabled': ConfigurationAdoptionDisposition.ADDED,
        'disabled': ConfigurationAdoptionDisposition.UNCHANGED,
        'removed': ConfigurationAdoptionDisposition.REMOVED,
        'retained': ConfigurationAdoptionDisposition.UNCHANGED,
        're_enabled': ConfigurationAdoptionDisposition.ENABLED,
    }
    assert [change.identity.canonical_key for change in plan.changes] == sorted(
        change.identity.canonical_key for change in plan.changes
    )
    assert plan.is_adoptable
    assert plan.requires_execution_upgrade


def test_active_to_disabled_is_not_removed():
    source = _revision('a', defined=('rule',), executable=('rule',))
    target = _revision('b', defined=('rule',))
    assert _changes(plan_configuration_adoption(source, target)) == {
        'rule': ConfigurationAdoptionDisposition.DISABLED
    }


def test_disabled_to_removed_is_explicit_and_not_ready_for_legacy_executor():
    source = _revision('a', defined=('rule',))
    target = _revision('b')
    plan = plan_configuration_adoption(source, target)
    assert _changes(plan) == {'rule': ConfigurationAdoptionDisposition.REMOVED}
    assert plan.requires_execution_upgrade


def test_priority_order_change_remains_compatible():
    source = _revision('a', defined=('rule',), executable=('rule',), order=1)
    target = _revision('b', defined=('rule',), executable=('rule',), order=2)
    assert _changes(plan_configuration_adoption(source, target)) == {
        'rule': ConfigurationAdoptionDisposition.COMPATIBLE
    }


def test_existing_priority_group_rejection_policy_is_preserved():
    source = _revision('a', defined=('rule',), executable=('rule',))
    target = _revision('b', defined=('rule',), executable=('rule',), group='group-b')
    plan = plan_configuration_adoption(source, target)
    assert not plan.is_adoptable
    assert plan.rejected_changes[0].rejection_reason is (
        ConfigurationAdoptionRejectionReason.PRIORITY_GROUP_CHANGED
    )


def test_existing_evaluator_rejection_policy_is_preserved():
    source = _revision('a', defined=('rule',), executable=('rule',))
    target = _revision('b', defined=('rule',), executable=('rule',), evaluator='alternate')
    plan = plan_configuration_adoption(source, target)
    assert plan.rejected_changes[0].rejection_reason is (
        ConfigurationAdoptionRejectionReason.EVALUATOR_CHANGED
    )


def test_criticality_change_preserves_structural_reset_policy():
    source = _revision('a', defined=('rule',), executable=('rule',))
    target = _revision('b', defined=('rule',), executable=('rule',), criticality=Criticality.C2)
    plan = plan_configuration_adoption(source, target)
    assert _changes(plan) == {'rule': ConfigurationAdoptionDisposition.STRUCTURAL_RESET}
    assert plan.structural_reset_groups == ('group-a',)


def test_alarm_kind_change_preserves_rejection_policy():
    source = _revision('a', defined=('rule',), executable=('rule',))
    target = _revision('b', defined=('rule',), executable=('rule',), kind=AlarmKind.IMPACT)
    plan = plan_configuration_adoption(source, target)
    assert plan.rejected_changes[0].rejection_reason is (
        ConfigurationAdoptionRejectionReason.ALARM_KIND_CHANGED
    )


def test_distinct_releases_preserve_artifact_reference_and_can_plan():
    source = _revision('a', defined=('rule',), executable=('rule',))
    target = _revision(
        'b', defined=('rule',), executable=('rule',), key=AlarmResolutionKey('R11', 'C6')
    )
    plan = plan_configuration_adoption(source, target)
    assert source.revision_key == ('R10', 'C5')
    assert target.revision_key == ('R11', 'C6')
    assert plan.target.artifact_ref.resolution_key == AlarmResolutionKey('R11', 'C6')


def test_manually_incomplete_universe_is_rejected():
    source = _revision('a', defined=('disabled',))
    target = _revision('b', defined=('added',))
    with pytest.raises(ConfigurationAdoptionPlanError, match='source and target defined'):
        ConfigurationAdoptionPlan(source=source, target=target, changes=())


def test_manually_misclassified_enabled_transition_is_rejected():
    source = _revision('a', defined=('rule',), executable=('rule',))
    target = _revision('b', defined=('rule',), executable=('rule',))
    with pytest.raises(ConfigurationAdoptionPlanError, match='enabled alarm'):
        ConfigurationAdoptionPlan(
            source=source,
            target=target,
            changes=(
                ConfigurationAdoptionChange(
                    identity=_identity('rule'),
                    disposition=ConfigurationAdoptionDisposition.ENABLED,
                ),
            ),
        )


def test_revision_rejects_mismatched_artifact_and_session():
    source = _revision('a')
    with pytest.raises(AlarmConfigurationRevisionError, match='revision'):
        AlarmConfigurationRevision(
            artifact_ref=_ref('b', key=AlarmResolutionKey('R11', 'C5')),
            defined_alarm_identities=(),
            session=source.session,
        )


def test_builder_binds_ready_contract_to_registry_and_exact_artifact():
    key = AlarmResolutionKey('R10', 'C5')
    planned = _plan('rule', key)
    runtime = RuntimeAlarmConfiguration(
        resolution_key=key,
        defined_alarm_identities=(_identity('rule'), _identity('disabled')),
        planned_alarms=(planned,),
        parameters_by_alarm={_identity('rule'): {'limit': 10.0}},
    )
    manifest = {
        'source_key': 'alarm-configuration',
        'result_id': 'alarm-materialization-' + 'a' * 64,
        'status': 'READY',
        'resolution_key': {
            'alarm_configuration_revision': 'R10',
            'confirmed_tool_catalog_revision': 'C5',
        },
    }
    ready = ReadyAlarmMaterialization(
        result_id=manifest['result_id'],
        runtime=runtime,
        delivery=DeliveryAlarmConfiguration(resolution_key=key, alarms=()),
        manifest=manifest,
        manifest_sha256='f' * 64,
    )
    revision = build_alarm_configuration_revision(
        candidate=ready, evaluator_registry=_registry('threshold')
    )
    assert revision.artifact_ref.source_key == 'alarm-configuration'
    assert revision.artifact_ref.manifest_sha256 == 'f' * 64
    assert revision.session.identities == (_identity('rule'),)
    assert revision.is_defined(_identity('disabled'))
    with pytest.raises(ValueError, match='identity or resolution key'):
        build_alarm_configuration_revision(
            candidate=ReadyAlarmMaterialization(
                result_id=ready.result_id,
                runtime=runtime,
                delivery=ready.delivery,
                manifest={**manifest, 'status': 'BLOCKED'},
                manifest_sha256=ready.manifest_sha256,
            ),
            evaluator_registry=_registry('threshold'),
        )
    with pytest.raises(ValueError, match='registered'):
        build_alarm_configuration_revision(candidate=ready, evaluator_registry=_registry())
