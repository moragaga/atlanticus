from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Generic, TypeVar

from ada.web.tools.enums import ToolConfigurationKind, ToolScope
from ada.web.tools.structure import ToolComponent, ToolStructure, ToolSubcomponent
from ada_command_center.domain.alarms import (
    AlarmColor,
    AlarmConfiguration,
    AlarmConfigurationSnapshot,
    AlarmDeactivationDefinition,
    AlarmDefinition,
    AlarmEscalationDefinition,
    AlarmEscalationStepDefinition,
    AlarmIdentity,
    AlarmKind,
    AlarmVisualSubcomponentTarget,
    AlarmVisualTarget,
    BusinessCategory,
    Criticality,
    MessageDefinition,
    MessageScope,
    OperationalArea,
    ProcessAlarmProjectionMode,
    ReappearanceDefinition,
    VisibilityMode,
)
from ada_command_center.tools.catalog import (
    ToolCatalogEntry,
    ToolCatalogSnapshot,
    ToolCatalogStore,
    create_tool_catalog_snapshot,
)
from ada_command_center.web.alarms.configuration.source_projection import (
    create_alarm_configuration_projection_service,
)
from ada_command_center.web.alarms.configuration.source_release import (
    AlarmConfigurationSourceService,
)
from ada_command_center.web.alarms.configuration.tool_dependencies import (
    select_alarm_tool_dependencies,
)
from ada_command_center.web.alarms.configuration.tool_references import (
    AlarmToolReferenceCatalog,
    AlarmToolReferenceReader,
)
from ada_command_center.web.application.configuration_manager.application import (
    create_configuration_manager_application,
)
from ada_command_center.web.application.configuration_manager.composition import (
    ALARM_CONFIGURATION_MANAGER_ACCESS_KEY,
    ALARM_CONFIGURATION_SOURCE_KEY,
)
from ada_command_center.web.application.configuration_manager.dependencies import (
    ConfigurationManagerDependencies,
)
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.models import WebApplicationRuntime
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.local import LocalSourceSettings, LocalSourceStore
from atlanticus.web.source.models import SourceKey, SourceReleaseId

PayloadT = TypeVar('PayloadT')


# Store efímero usado sólo por el runtime local de prueba.
class InProcessProjectionStore(ProjectionStore[PayloadT], Generic[PayloadT]):
    def __init__(self) -> None:
        self._active: dict[SourceKey, ProjectionRecord[PayloadT]] = {}

    def get_active(self, source_key: SourceKey) -> ProjectionRecord[PayloadT] | None:
        return self._active.get(source_key)

    def replace_active(
        self,
        projection: ProjectionRecord[PayloadT],
    ) -> ProjectionRecord[PayloadT]:
        self._active[projection.source_key] = projection
        return projection


class InProcessToolCatalogStore(ToolCatalogStore):
    def __init__(self, snapshot: ToolCatalogSnapshot | None = None) -> None:
        self._snapshot = snapshot

    def get_current(self) -> ToolCatalogSnapshot | None:
        return self._snapshot

    def replace_current(self, snapshot: ToolCatalogSnapshot) -> ToolCatalogSnapshot:
        self._snapshot = snapshot
        return snapshot


def create_local_configuration_manager_dependencies(
    *,
    source_root: Path | None = None,
    seed_sample_configuration: bool = True,
) -> ConfigurationManagerDependencies:
    root = source_root or _source_root()
    source_store = LocalSourceStore(LocalSourceSettings(root=root))
    projection_store = InProcessProjectionStore[AlarmConfigurationSnapshot]()
    tool_catalog_snapshot = create_local_tool_catalog_snapshot()
    tool_catalog_store = InProcessToolCatalogStore(tool_catalog_snapshot)
    tool_reference_reader = AlarmToolReferenceReader(store=tool_catalog_store)
    # Una sola lectura del catálogo alimenta UI y el manifest durable del seed local.
    tool_references = tool_reference_reader.load()
    if tool_references is None:
        raise RuntimeError('Local Confirmed Tool Catalog could not be created')
    principal = ManagerPrincipal(
        subject_id='local',
        display_name='Administrador local',
        access_keys=(ALARM_CONFIGURATION_MANAGER_ACCESS_KEY,),
        is_local=True,
    )
    if seed_sample_configuration:
        _seed_alarm_configuration(
            source_store,
            projection_store,
            tool_references=tool_references,
        )
    return ConfigurationManagerDependencies(
        source_store=source_store,
        projection_store=projection_store,
        principal_provider=lambda: principal,
        tool_reference_reader=tool_reference_reader,
        source_name='Local Source',
        projection_name='In-process Projection',
    )


def create_local_configuration_manager_application(
    *,
    source_root: Path | None = None,
    seed_sample_configuration: bool = True,
) -> WebApplicationRuntime:
    return create_configuration_manager_application(
        create_local_configuration_manager_dependencies(
            source_root=source_root,
            seed_sample_configuration=seed_sample_configuration,
        )
    )


def create_local_tool_catalog_snapshot() -> ToolCatalogSnapshot:
    return create_tool_catalog_snapshot(
        (
            ToolCatalogEntry(
                tool_key='integrated_operations',
                display_name='Integrated Operations',
                kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
                source_release_id=SourceReleaseId('local-integrated-v1'),
                structure=ToolStructure(
                    tool_key='integrated_operations',
                    kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
                    components=(
                        ToolComponent(
                            key='mine_primary',
                            display_name='Mine Primary',
                            scope=ToolScope.MINE,
                            subcomponents=(
                                ToolSubcomponent(
                                    key='crusher',
                                    display_name='Crusher',
                                    linked_component_keys=('mine_secondary',),
                                ),
                                ToolSubcomponent(
                                    key='stockpile',
                                    display_name='Stockpile',
                                ),
                            ),
                        ),
                        ToolComponent(
                            key='mine_secondary',
                            display_name='Mine Secondary',
                            scope=ToolScope.MINE,
                            subcomponents=(
                                ToolSubcomponent(
                                    key='haulage',
                                    display_name='Haulage',
                                ),
                            ),
                        ),
                    ),
                ),
            ),
            ToolCatalogEntry(
                tool_key='process_control',
                display_name='Process Control',
                kind=ToolConfigurationKind.PROCESS,
                source_release_id=SourceReleaseId('local-process-v1'),
                structure=ToolStructure(
                    tool_key='process_control',
                    kind=ToolConfigurationKind.PROCESS,
                    operational_scope=ToolScope.PLANT,
                    components=(
                        ToolComponent(
                            key='plant_process',
                            display_name='Plant Process',
                            subcomponents=(
                                ToolSubcomponent(
                                    key='line_a',
                                    display_name='Line A',
                                ),
                                ToolSubcomponent(
                                    key='line_b',
                                    display_name='Line B',
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
        generated_at_utc=datetime(2026, 9, 21, 18, 0, tzinfo=UTC),
    )


def create_sample_alarm_configuration() -> AlarmConfiguration:
    global_message = MessageDefinition(
        message_key='operations-alert',
        scope=MessageScope.GLOBAL,
        display_text='Operational alarm requires attention.',
        is_active=True,
    )
    family_message = MessageDefinition(
        message_key='mine-crushing-alert',
        scope=MessageScope.FAMILY,
        family_key='mine-crushing',
        display_text='Mine crushing condition requires coordinated response.',
        is_active=True,
    )
    special_identity = AlarmIdentity(
        family_key='mine-crushing',
        alarm_key='crusher-trip',
    )
    special_condition = AlarmDefinition(
        identity=special_identity,
        rule_name='crusher-trip',
        display_name='Crusher Trip',
        title='Crusher trip detected',
        cause_template='Crusher trip state is active.',
        is_active=True,
        visibility_mode=VisibilityMode.TRACE_ONLY,
        is_special_condition=True,
        kind=AlarmKind.IMPACT,
        criticality=Criticality.C1,
        business_category=BusinessCategory.PRODUCTIVITY,
        operational_areas=(OperationalArea.MINE,),
        color=AlarmColor.RED,
        evaluator_key='local.crusher-trip',
        parameters={'enabled': True},
        priority_group='mine-crushing-priority',
        priority_order=1,
        message_keys=('operations-alert',),
        reappearance=ReappearanceDefinition(),
        default_deactivation=AlarmDeactivationDefinition(
            enabled=False,
            max_duration_hours=None,
            approval_required=False,
        ),
        escalation=AlarmEscalationDefinition(
            origin_tool_key='integrated_operations',
        ),
        visual_targets=(
            AlarmVisualTarget(
                tool_key='integrated_operations',
                component_keys=('mine_primary',),
                subcomponents=(
                    AlarmVisualSubcomponentTarget(
                        owner_component_key='mine_primary',
                        subcomponent_key='crusher',
                    ),
                ),
            ),
        ),
    )
    primary_alarm = AlarmDefinition(
        identity=AlarmIdentity(
            family_key='mine-crushing',
            alarm_key='crusher-throughput-risk',
        ),
        rule_name='crusher-throughput-risk',
        display_name='Crusher Throughput Risk',
        title='Crusher throughput is at risk',
        cause_template='Crusher throughput is below {threshold_tph} tph.',
        is_active=True,
        visibility_mode=VisibilityMode.VISIBLE,
        is_special_condition=False,
        kind=AlarmKind.RISK,
        criticality=Criticality.C2,
        business_category=BusinessCategory.PRODUCTIVITY,
        operational_areas=(OperationalArea.MINE, OperationalArea.PLANT),
        color=AlarmColor.YELLOW,
        evaluator_key='local.threshold',
        parameters={
            'threshold_tph': 1200.0,
            'window': '15m',
            'quality_required': True,
        },
        priority_group='mine-crushing-priority',
        priority_order=2,
        message_keys=('operations-alert', 'mine-crushing-alert'),
        reappearance=ReappearanceDefinition(
            after_minutes=15,
            special_conditions=(special_identity,),
        ),
        default_deactivation=AlarmDeactivationDefinition(
            enabled=True,
            max_duration_hours=4,
            approval_required=True,
        ),
        escalation=AlarmEscalationDefinition(
            origin_tool_key='integrated_operations',
            steps=(
                AlarmEscalationStepDefinition(
                    step_order=1,
                    target_tool_key='process_control',
                    is_enabled=True,
                    wait_minutes_from_previous_step=10,
                ),
            ),
        ),
        visual_targets=(
            AlarmVisualTarget(
                tool_key='integrated_operations',
                component_keys=('mine_primary', 'mine_secondary'),
                subcomponents=(
                    AlarmVisualSubcomponentTarget(
                        owner_component_key='mine_primary',
                        subcomponent_key='crusher',
                    ),
                    AlarmVisualSubcomponentTarget(
                        owner_component_key='mine_secondary',
                        subcomponent_key='haulage',
                    ),
                ),
            ),
            AlarmVisualTarget(
                tool_key='process_control',
                component_keys=('plant_process',),
                subcomponents=(
                    AlarmVisualSubcomponentTarget(
                        owner_component_key='plant_process',
                        subcomponent_key='line_a',
                    ),
                ),
                process_projection_mode=ProcessAlarmProjectionMode.DISTRIBUTED,
            ),
        ),
    )
    return AlarmConfiguration(
        rules=(special_condition, primary_alarm),
        messages=(global_message, family_message),
    )


def _seed_alarm_configuration(
    source_store: LocalSourceStore,
    projection_store: InProcessProjectionStore[AlarmConfigurationSnapshot],
    *,
    tool_references: AlarmToolReferenceCatalog,
) -> None:
    source = AlarmConfigurationSourceService(
        source=source_store,
        source_key=ALARM_CONFIGURATION_SOURCE_KEY,
    )
    snapshot = source.get_current()
    if snapshot.current is None:
        # El seed reproduce producción: persiste sólo las Tools realmente referenciadas.
        configuration = create_sample_alarm_configuration()
        source.publish_snapshot(
            AlarmConfigurationSnapshot(
                configuration=configuration,
                tool_dependencies=select_alarm_tool_dependencies(
                    configuration,
                    tool_references.dependencies,
                ),
            ),
            published_by='local-bootstrap',
            expected_concurrency_token=snapshot.concurrency_token,
            basis_release=None,
        )
    projection = create_alarm_configuration_projection_service(
        source=source_store,
        projection=projection_store,
    )
    target = projection.select_current_target(ALARM_CONFIGURATION_SOURCE_KEY)
    if target is not None:
        projection.project(target)


def _source_root() -> Path:
    configured = os.getenv('ADA_COMMAND_CENTER_CONFIGURATION_MANAGER_SOURCE_ROOT')
    if configured is not None and configured.strip():
        return Path(configured).expanduser().resolve()
    return Path.cwd() / '.runtime' / 'configuration-manager' / 'source'
