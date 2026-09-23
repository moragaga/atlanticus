from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from ada_command_center.domain.alarms import AlarmConfigurationSnapshot
from ada_command_center.web.alarms.configuration.source_projection import (
    create_alarm_configuration_projection_service,
)
from ada_command_center.web.alarms.configuration.source_release import (
    AlarmConfigurationSourceService,
)
from ada_command_center.web.alarms.configuration.tool_references import AlarmToolReferenceReader
from ada_command_center.web.alarms.configuration.web import (
    AlarmConfigurationAdminWebContext,
    build_alarm_configuration_admin,
    build_alarm_configuration_history_preview,
    create_alarm_configuration_admin_web_module,
)
from ada_command_center.web.alarms.configuration.workflows import (
    AlarmConfigurationAuditActorProvider,
    AlarmConfigurationManagerDraftValidationWorkflow,
    AlarmConfigurationManagerSourceWorkflow,
)
from ada_command_center.web.alarms.configuration.workspace import (
    AlarmConfigurationManagerWorkspaceBinding,
)
from atlanticus.web.manager.authorization import (
    DefaultManagerAuthorizationPolicy,
    ManagerAuthorizationPolicy,
)
from atlanticus.web.manager.models import ManagerModule, ManagerPrincipal
from atlanticus.web.manager.web.ids import (
    workflow_action_id,
    workflow_draft_id,
    workflow_editor_revision_id,
    workflow_saved_draft_id,
)
from atlanticus.web.projection.service import SourceProjectionService
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.models import SourceKey
from atlanticus.web.source.store import SourceStore

ALARM_CONFIGURATION_MANAGER_SOURCE_SERVICE = 'ada-command-center.alarms.configuration.source'
ALARM_CONFIGURATION_MANAGER_PROJECTION_SERVICE = (
    'ada-command-center.alarms.configuration.projection'
)
ALARM_CONFIGURATION_MANAGER_VALIDATION_SERVICE = (
    'ada-command-center.alarms.configuration.validation'
)

AlarmConfigurationPrincipalProvider = Callable[[], ManagerPrincipal]


@dataclass(frozen=True, slots=True)
class AlarmConfigurationManagerComposition:
    module: ManagerModule
    source_workflow: AlarmConfigurationManagerSourceWorkflow
    projection_service: SourceProjectionService[AlarmConfigurationSnapshot]
    validation_workflow: AlarmConfigurationManagerDraftValidationWorkflow


def compose_alarm_configuration_manager(
    *,
    source_store: SourceStore,
    projection_store: ProjectionStore[AlarmConfigurationSnapshot],
    principal_provider: AlarmConfigurationPrincipalProvider,
    source_key: SourceKey,
    group_key: str,
    access_key: str,
    tool_reference_reader: AlarmToolReferenceReader | None = None,
    module_key: str = 'alarm-configuration',
    route: str = '/alarm-configuration',
    order: int = 10,
    title: str = 'Alarm Configuration',
    description: str = 'Rules and Messages for the ADA Command Center alarm domain.',
    source_name: str = 'Alarm Configuration Source',
    projection_name: str = 'Alarm Configuration Projection',
    authorization: ManagerAuthorizationPolicy | None = None,
    audit_actor_provider: AlarmConfigurationAuditActorProvider | None = None,
) -> AlarmConfigurationManagerComposition:
    resolved_authorization = authorization or DefaultManagerAuthorizationPolicy()
    resolved_actor_provider = audit_actor_provider or (lambda: principal_provider().subject_id)
    source_service = AlarmConfigurationSourceService(
        source=source_store,
        source_key=source_key,
    )
    source_workflow = AlarmConfigurationManagerSourceWorkflow(
        source=source_service,
        audit_actor_provider=resolved_actor_provider,
        tool_reference_provider=(
            (lambda: None) if tool_reference_reader is None else tool_reference_reader.load
        ),
    )
    validation_workflow = AlarmConfigurationManagerDraftValidationWorkflow(
        audit_actor_provider=resolved_actor_provider,
    )
    projection_service = create_alarm_configuration_projection_service(
        source=source_store,
        projection=projection_store,
    )
    workspace = AlarmConfigurationManagerWorkspaceBinding(
        source=source_workflow,
        principal_provider=principal_provider,
    )

    context = AlarmConfigurationAdminWebContext(
        workspace_payload_reader=workspace.load_payload,
        workspace_payload_writer=workspace.save_payload,
        draft_store_id=workflow_draft_id(module_key),
        saved_draft_store_id=workflow_saved_draft_id(module_key),
        draft_save_action_id=workflow_action_id(module_key, 'save-draft'),
        editor_revision_store_id=workflow_editor_revision_id(module_key),
        tool_reference_provider=(
            None if tool_reference_reader is None else tool_reference_reader.load
        ),
        can_manage=lambda: resolved_authorization.can_view(principal_provider(), module),
        source_name=source_name,
        projection_name=projection_name,
    )

    def layout(_services: ServiceRegistry) -> object:
        return build_alarm_configuration_admin(context)

    web_module = create_alarm_configuration_admin_web_module(context)

    def register_services(services: ServiceRegistry) -> None:
        services.add(ALARM_CONFIGURATION_MANAGER_SOURCE_SERVICE, source_workflow)
        services.add(ALARM_CONFIGURATION_MANAGER_PROJECTION_SERVICE, projection_service)
        services.add(ALARM_CONFIGURATION_MANAGER_VALIDATION_SERVICE, validation_workflow)

    module = ManagerModule(
        key=module_key,
        group_key=group_key,
        title=title,
        route=route,
        order=order,
        description=description,
        layout=layout,
        source_key=source_key,
        source_service=ALARM_CONFIGURATION_MANAGER_SOURCE_SERVICE,
        source_reader_service=ALARM_CONFIGURATION_MANAGER_SOURCE_SERVICE,
        source_history_service=ALARM_CONFIGURATION_MANAGER_SOURCE_SERVICE,
        projection_service=ALARM_CONFIGURATION_MANAGER_PROJECTION_SERVICE,
        draft_validation_service=ALARM_CONFIGURATION_MANAGER_VALIDATION_SERVICE,
        access_key=access_key,
        web_module=replace(web_module, register_services=register_services),
        source_name=source_name,
        projection_name=projection_name,
        history_preview_renderer=build_alarm_configuration_history_preview,
    )
    return AlarmConfigurationManagerComposition(
        module=module,
        source_workflow=source_workflow,
        projection_service=projection_service,
        validation_workflow=validation_workflow,
    )
