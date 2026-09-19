from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from atlanticus.web.compositions.navigation_manager.workflows import (
    NavigationAuditActorProvider,
    NavigationManagerDraftValidationWorkflow,
    NavigationManagerSourceWorkflow,
)
from atlanticus.web.compositions.navigation_manager.workspace import (
    NavigationManagerWorkspaceBinding,
)
from atlanticus.web.manager.authorization import (
    DefaultManagerAuthorizationPolicy,
    ManagerAuthorizationPolicy,
)
from atlanticus.web.manager.models import (
    ManagerModule,
    ManagerModuleAccess,
    ManagerPrincipal,
)
from atlanticus.web.manager.web.ids import (
    workflow_action_id,
    workflow_draft_id,
    workflow_editor_revision_id,
    workflow_saved_draft_id,
)
from atlanticus.web.navigation.configuration.models import NavigationConfigurationCatalog
from atlanticus.web.navigation.configuration.profiles import NavigationProfileCatalogProvider
from atlanticus.web.navigation.configuration.source_projection import (
    NavigationProjectionValidator,
    create_navigation_profile_catalog_validator,
    create_navigation_projection_service,
)
from atlanticus.web.navigation.configuration.source_release import NavigationSourceService
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.models import SourceKey
from atlanticus.web.source.store import SourceStore

NAVIGATION_CONFIGURATION_SOURCE_KEY = SourceKey('navigation-configuration')
NAVIGATION_MANAGER_SOURCE_SERVICE = 'navigation.configuration.source'
NAVIGATION_MANAGER_PROJECTION_SERVICE = 'navigation.configuration.projection'
NAVIGATION_MANAGER_VALIDATION_SERVICE = 'navigation.configuration.validation'

NavigationPrincipalProvider = Callable[[], ManagerPrincipal]


@dataclass(frozen=True, slots=True)
class NavigationManagerComposition:
    module: ManagerModule
    source_workflow: NavigationManagerSourceWorkflow
    projection_service: object
    validation_workflow: NavigationManagerDraftValidationWorkflow


def compose_navigation_manager(
    *,
    services: ServiceRegistry,
    source_store: SourceStore,
    projection_store: ProjectionStore[NavigationConfigurationCatalog],
    principal_provider: NavigationPrincipalProvider,
    group_key: str,
    module_key: str = 'navigation',
    route: str = '/navigation',
    order: int = 20,
    title: str = 'Navigation',
    source_key: SourceKey = NAVIGATION_CONFIGURATION_SOURCE_KEY,
    access: ManagerModuleAccess | None = None,
    authorization: ManagerAuthorizationPolicy | None = None,
    audit_actor_provider: NavigationAuditActorProvider | None = None,
    profile_catalog_provider: NavigationProfileCatalogProvider | None = None,
    validators: tuple[NavigationProjectionValidator, ...] = (),
) -> NavigationManagerComposition:
    resolved_access = access or ManagerModuleAccess()
    resolved_authorization = authorization or DefaultManagerAuthorizationPolicy()
    resolved_actor_provider = audit_actor_provider or (lambda: principal_provider().subject_id)
    resolved_validators = (
        (create_navigation_profile_catalog_validator(profile_catalog_provider), *validators)
        if profile_catalog_provider is not None
        else validators
    )
    source_service = NavigationSourceService(source=source_store, source_key=source_key)
    source_workflow = NavigationManagerSourceWorkflow(
        source=source_service,
        audit_actor_provider=resolved_actor_provider,
    )
    validation_workflow = NavigationManagerDraftValidationWorkflow(
        audit_actor_provider=resolved_actor_provider,
        validators=resolved_validators,
    )
    projection_service = create_navigation_projection_service(
        source=source_store,
        projection=projection_store,
        validators=resolved_validators,
    )
    workspace = NavigationManagerWorkspaceBinding(
        source=source_workflow,
        principal_provider=principal_provider,
    )

    from atlanticus.web.navigation.configuration.web import (
        NavigationAdminWebContext,
        build_navigation_admin_configuration,
        build_navigation_history_preview,
        create_navigation_admin_web_module,
    )

    context = NavigationAdminWebContext(
        workspace_payload_reader=workspace.load_payload,
        workspace_payload_writer=workspace.save_payload,
        draft_store_id=workflow_draft_id(module_key),
        saved_draft_store_id=workflow_saved_draft_id(module_key),
        draft_save_action_id=workflow_action_id(module_key, 'save-draft'),
        editor_revision_store_id=workflow_editor_revision_id(module_key),
        can_manage=lambda: resolved_authorization.can_publish(
            principal_provider(),
            module,
        ),
        source_name='Navigation Source',
        projection_name='Navigation Projection',
        profile_catalog_provider=profile_catalog_provider,
    )

    def layout(_services: ServiceRegistry) -> object:
        return build_navigation_admin_configuration(context)

    module = ManagerModule(
        key=module_key,
        group_key=group_key,
        title=title,
        route=route,
        order=order,
        layout=layout,
        source_key=source_key,
        source_service=NAVIGATION_MANAGER_SOURCE_SERVICE,
        source_reader_service=NAVIGATION_MANAGER_SOURCE_SERVICE,
        source_history_service=NAVIGATION_MANAGER_SOURCE_SERVICE,
        projection_service=NAVIGATION_MANAGER_PROJECTION_SERVICE,
        draft_validation_service=NAVIGATION_MANAGER_VALIDATION_SERVICE,
        access=resolved_access,
        web_module=create_navigation_admin_web_module(context),
        history_preview_renderer=build_navigation_history_preview,
        source_name='Navigation Source',
        projection_name='Navigation Projection',
    )
    services.add(NAVIGATION_MANAGER_SOURCE_SERVICE, source_workflow)
    services.add(NAVIGATION_MANAGER_PROJECTION_SERVICE, projection_service)
    services.add(NAVIGATION_MANAGER_VALIDATION_SERVICE, validation_workflow)
    return NavigationManagerComposition(
        module=module,
        source_workflow=source_workflow,
        projection_service=projection_service,
        validation_workflow=validation_workflow,
    )
