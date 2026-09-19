from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from atlanticus.web.compositions.profiles_manager.workflows import (
    ProfilesAuditActorProvider,
    ProfilesManagerDraftValidationWorkflow,
    ProfilesManagerSourceWorkflow,
)
from atlanticus.web.compositions.profiles_manager.workspace import ProfilesManagerWorkspaceBinding
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
from atlanticus.web.profiles.configuration.source_projection import (
    create_profiles_projection_service,
)
from atlanticus.web.profiles.configuration.source_release import ProfilesSourceService
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.models import SourceKey
from atlanticus.web.source.store import SourceStore

PROFILES_CONFIGURATION_SOURCE_KEY = SourceKey('profiles-configuration')
PROFILES_MANAGER_SOURCE_SERVICE = 'profiles.configuration.source'
PROFILES_MANAGER_PROJECTION_SERVICE = 'profiles.configuration.projection'
PROFILES_MANAGER_VALIDATION_SERVICE = 'profiles.configuration.validation'

ProfilesPrincipalProvider = Callable[[], ManagerPrincipal]


@dataclass(frozen=True, slots=True)
class ProfilesManagerComposition:
    module: ManagerModule
    source_workflow: ProfilesManagerSourceWorkflow
    projection_service: object
    validation_workflow: ProfilesManagerDraftValidationWorkflow


# Compone Profiles con Manager sin introducir dependencias de ADA ni lógica de consumo runtime.
def compose_profiles_manager(
    *,
    services: ServiceRegistry,
    source_store: SourceStore,
    projection_store: ProjectionStore[ProfileCatalog],
    principal_provider: ProfilesPrincipalProvider,
    group_key: str,
    module_key: str = 'profiles',
    route: str = '/profiles',
    order: int = 10,
    title: str = 'Profiles',
    source_key: SourceKey = PROFILES_CONFIGURATION_SOURCE_KEY,
    access_key: str | None = None,
    authorization: ManagerAuthorizationPolicy | None = None,
    audit_actor_provider: ProfilesAuditActorProvider | None = None,
) -> ProfilesManagerComposition:
    resolved_authorization = authorization or DefaultManagerAuthorizationPolicy()
    resolved_actor_provider = audit_actor_provider or (lambda: principal_provider().subject_id)
    source_service = ProfilesSourceService(source=source_store, source_key=source_key)
    source_workflow = ProfilesManagerSourceWorkflow(
        source=source_service,
        audit_actor_provider=resolved_actor_provider,
    )
    validation_workflow = ProfilesManagerDraftValidationWorkflow(
        audit_actor_provider=resolved_actor_provider,
    )
    projection_service = create_profiles_projection_service(
        source=source_store,
        projection=projection_store,
    )
    workspace = ProfilesManagerWorkspaceBinding(
        source=source_workflow,
        principal_provider=principal_provider,
    )

    # La dependencia Web se carga sólo al componer la superficie administrativa.
    from atlanticus.web.profiles.configuration.web import (
        LocalIdentityBadge,
        ProfilesAdminWebContext,
        build_profiles_admin_configuration,
        create_profiles_admin_web_module,
    )
    from atlanticus.web.users.local import LOCAL_USERS

    # Users conserva ownership de Jane/John; composición sólo traduce su presentación al contrato Profiles.
    def local_identity_badges():
        return tuple(
            LocalIdentityBadge(
                display_name=user.display_name,
                background_color=user.avatar_background_color,
                text_color=user.avatar_text_color,
            )
            for user in LOCAL_USERS
        )

    context = ProfilesAdminWebContext(
        workspace_payload_reader=workspace.load_payload,
        workspace_payload_writer=workspace.save_payload,
        local_identity_badges_provider=local_identity_badges,
        draft_store_id=workflow_draft_id(module_key),
        saved_draft_store_id=workflow_saved_draft_id(module_key),
        draft_save_action_id=workflow_action_id(module_key, 'save-draft'),
        editor_revision_store_id=workflow_editor_revision_id(module_key),
        # ManagerAuthorizationPolicy expone can_view; Profiles no replica el desvío can_access de Navigation.
        can_manage=lambda: resolved_authorization.can_view(
            principal_provider(),
            module,
        ),
        source_name='Profiles Source',
    )

    def layout(_services: ServiceRegistry) -> object:
        return build_profiles_admin_configuration(context)

    module = ManagerModule(
        key=module_key,
        group_key=group_key,
        title=title,
        route=route,
        order=order,
        layout=layout,
        source_key=source_key,
        source_service=PROFILES_MANAGER_SOURCE_SERVICE,
        source_reader_service=PROFILES_MANAGER_SOURCE_SERVICE,
        source_history_service=PROFILES_MANAGER_SOURCE_SERVICE,
        projection_service=PROFILES_MANAGER_PROJECTION_SERVICE,
        draft_validation_service=PROFILES_MANAGER_VALIDATION_SERVICE,
        access_key=access_key,
        web_module=create_profiles_admin_web_module(context),
        source_name='Profiles Source',
        projection_name='Profiles Projection',
    )
    services.add(PROFILES_MANAGER_SOURCE_SERVICE, source_workflow)
    services.add(PROFILES_MANAGER_PROJECTION_SERVICE, projection_service)
    services.add(PROFILES_MANAGER_VALIDATION_SERVICE, validation_workflow)
    return ProfilesManagerComposition(
        module=module,
        source_workflow=source_workflow,
        projection_service=projection_service,
        validation_workflow=validation_workflow,
    )
