from ada.alarms.core import AlarmResolutionKey, AlarmRouting, PlannedAlarm
from ada.alarms.materialization import (
    AlarmConfigurationResolution,
    AlarmMaterializationProvenance,
    AlarmResolutionFinding,
    AlarmResolutionFindingSeverity,
    AlarmResolutionStatus,
    DeliveryAlarmConfiguration,
    EngineAlarmConfiguration,
    ModelerAlarmConfiguration,
    ResolvedDeactivationPolicy,
    ResolvedModelerAlarm,
    ResolvedVisualTarget,
)
from ada.contracts.alarms import (
    AlarmColor,
    AlarmIdentity,
    AlarmKind,
    BusinessCategory,
    Criticality,
    OperationalArea,
    ProcessAlarmProjectionMode,
    VisibilityMode,
)
from ada.contracts.tools.enums import ToolConfigurationKind


def provenance(
    *,
    release: str = 'ALARMS-7',
    tool_revision: str = 'TOOLS-4',
    projection_digest: str = 'a' * 64,
    qualification_digest: str = 'b' * 64,
) -> AlarmMaterializationProvenance:
    return AlarmMaterializationProvenance(
        source_release_id=release,
        source_published_at_utc='2026-10-07T10:00:00+00:00',
        confirmed_tool_catalog_revision=tool_revision,
        projection_digest=projection_digest,
        qualification_digest=qualification_digest,
        qualification_producer='manual-qualification',
        qualification_evidence_ref='qualification-7',
        qualified_at_utc='2026-10-07T10:05:00+00:00',
    )


def ready_resolution(
    *,
    release: str = 'ALARMS-7',
    tool_revision: str = 'TOOLS-4',
) -> AlarmConfigurationResolution:
    key = AlarmResolutionKey(release, tool_revision)
    identity = AlarmIdentity('mill', 'risk')
    plan = PlannedAlarm(
        identity=identity,
        kind=AlarmKind.RISK,
        criticality=Criticality.C1,
        priority_group='mill_feed',
        priority_order=1,
        evaluator_key='threshold',
        alarm_configuration_revision=release,
        tool_registry_revision=tool_revision,
        routing=AlarmRouting(origin_tool_key='tool_a'),
    )
    engine = EngineAlarmConfiguration(
        resolution_key=key,
        defined_alarm_identities=(identity,),
        planned_alarms=(plan,),
        parameters_by_alarm={identity: {'limit': 10.0}},
    )
    modeler = ModelerAlarmConfiguration(
        resolution_key=key,
        alarms=(
            ResolvedModelerAlarm(
                identity=identity,
                is_active=True,
                visibility_mode=VisibilityMode.VISIBLE,
                display_name='Risk',
                title='Risk alarm',
                cause_template='Value exceeds threshold',
                kind=AlarmKind.RISK,
                criticality=Criticality.C1,
                business_category=BusinessCategory.PRODUCTIVITY,
                operational_areas=(OperationalArea.PLANT,),
                color=AlarmColor.YELLOW,
                priority_group='mill_feed',
                priority_order=1,
                default_deactivation_policy=ResolvedDeactivationPolicy(
                    enabled=False,
                    max_duration_hours=None,
                    approval_required=False,
                ),
                visual_targets=(
                    ResolvedVisualTarget(
                        tool_key='tool_a',
                        tool_kind=ToolConfigurationKind.PROCESS,
                        process_projection_mode=ProcessAlarmProjectionMode.GENERIC,
                    ),
                ),
            ),
        ),
    )
    delivery = DeliveryAlarmConfiguration(
        resolution_key=key,
        publication_tool_keys=('tool_a',),
    )
    return AlarmConfigurationResolution(
        resolution_key=key,
        status=AlarmResolutionStatus.READY,
        findings=(),
        engine_configuration=engine,
        modeler_configuration=modeler,
        delivery_configuration=delivery,
    )


def blocked_resolution(
    *,
    release: str = 'ALARMS-8',
    tool_revision: str = 'TOOLS-4',
) -> AlarmConfigurationResolution:
    return AlarmConfigurationResolution(
        resolution_key=AlarmResolutionKey(release, tool_revision),
        status=AlarmResolutionStatus.BLOCKED,
        findings=(
            AlarmResolutionFinding(
                code='missing_tool',
                severity=AlarmResolutionFindingSeverity.BLOCKING,
                message='Tool is missing',
                reference_key='tool_missing',
            ),
        ),
    )
