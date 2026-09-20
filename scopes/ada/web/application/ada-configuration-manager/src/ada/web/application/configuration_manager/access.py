from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime

from ada.web.access.configuration import (
    AdaAccessConfiguration,
    AdaAccessConfigurationSourceError,
    AdaAccessSourceService,
)
from ada.web.access.configuration.web import (
    AdaAccessAdminWebContext,
    build_ada_access_admin_configuration,
    create_ada_access_admin_web_module,
)
from ada.web.application.configuration_manager.workspace import ManagerWorkspaceBridge
from atlanticus.web.manager import (
    DraftValidationResult,
    ManagerModule,
    ManagerPrincipal,
    ProjectionAuditRecord,
    ProjectionIssue,
    ProjectionSummaryItem,
    SourceHistoryReadResult,
    SourcePublicationResult,
    SourceReadResult,
    build_workspace_revision,
)
from atlanticus.web.manager.web.ids import (
    workflow_action_id,
    workflow_draft_id,
    workflow_editor_revision_id,
    workflow_saved_draft_id,
)
from atlanticus.web.profiles.errors import ProfilesDefinitionError
from atlanticus.web.profiles.models import ProfileCatalog
from atlanticus.web.projection.service import SourceProjectionService
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.services import ServiceRegistry
from atlanticus.web.source.models import HistoryPage, SourceKey, SourceReleaseRef, SourceSnapshot

ACCESS_MANAGER_ACCESS_KEY = 'access.manage'
ACCESS_SOURCE_SERVICE = 'ada.configuration-manager.access.source'
ACCESS_SOURCE_READER_SERVICE = 'ada.configuration-manager.access.source-reader'
ACCESS_SOURCE_HISTORY_SERVICE = 'ada.configuration-manager.access.source-history'
ACCESS_PROJECTION_SERVICE = 'ada.configuration-manager.access.projection'
ACCESS_DRAFT_VALIDATION_SERVICE = 'ada.configuration-manager.access.validation'


class AdaAccessManagerSourceWorkflow:
    def __init__(
        self,
        *,
        source: AdaAccessSourceService,
        audit_actor_provider: Callable[[], str],
    ) -> None:
        self._source = source
        self._audit_actor_provider = audit_actor_provider

    def get_source_snapshot(self) -> SourceSnapshot:
        return self._source.get_current()

    def load_current_source(self) -> SourceReadResult:
        snapshot = self._source.get_current()
        if snapshot.current is None:
            return SourceReadResult(snapshot=snapshot, payload=None)
        release = self._source.load_release(snapshot.current.release_ref)
        if self._source.get_current() != snapshot:
            raise AdaAccessConfigurationSourceError(
                'ADA access source changed while it was being loaded'
            )
        return SourceReadResult(
            snapshot=snapshot,
            payload=release.configuration.to_document(),
        )

    def list_history(self, *, limit: int = 20) -> HistoryPage:
        return self._source.query_history(page_size=limit)

    def load_history_release(
        self,
        release_ref: SourceReleaseRef,
    ) -> SourceHistoryReadResult:
        release = self._source.load_release(release_ref)
        return SourceHistoryReadResult(
            release_ref=release_ref,
            payload=release.configuration.to_document(),
        )

    def publish_draft(
        self,
        payload: dict[str, object],
        expected_source_snapshot: SourceSnapshot,
    ) -> SourcePublicationResult:
        if expected_source_snapshot.source_key != self._source.source_key:
            raise ValueError('Manager source snapshot uses a different source key')
        configuration = AdaAccessConfiguration.from_document(dict(payload))
        actor = _audit_actor(self._audit_actor_provider)
        basis_release = (
            expected_source_snapshot.current.release_ref
            if expected_source_snapshot.current is not None
            else None
        )
        published = self._source.publish_configuration(
            configuration,
            published_by=actor,
            expected_concurrency_token=expected_source_snapshot.concurrency_token,
            basis_release=basis_release,
        )
        return SourcePublicationResult(
            source=published,
            audit=ProjectionAuditRecord(
                actor=actor,
                occurred_at=published.release.release_ref.published_at_utc,
            ),
            summary=_summary(configuration),
        )


class AdaAccessManagerDraftValidationWorkflow:
    def __init__(
        self,
        *,
        profiles_projection: ProjectionStore[ProfileCatalog],
        profiles_source_key: SourceKey,
        audit_actor_provider: Callable[[], str],
    ) -> None:
        self._profiles_projection = profiles_projection
        self._profiles_source_key = profiles_source_key
        self._audit_actor_provider = audit_actor_provider

    def validate_draft(self, payload: dict[str, object]) -> DraftValidationResult:
        revision = build_workspace_revision(payload)
        audit = ProjectionAuditRecord(
            actor=_audit_actor(self._audit_actor_provider),
            occurred_at=datetime.now(UTC),
        )
        try:
            configuration = AdaAccessConfiguration.from_document(dict(payload))
            profiles = self._profiles_projection.get_active(self._profiles_source_key)
            if profiles is None:
                return _invalid(
                    revision,
                    audit,
                    code='access.profiles-projection.unavailable',
                    message='Profiles projection is not available',
                )
            if not isinstance(profiles.payload, ProfileCatalog):
                return _invalid(
                    revision,
                    audit,
                    code='access.profiles-projection.invalid',
                    message='Profiles projection payload is invalid',
                )
            configuration.validate_profiles(profiles.payload)
        except (ValueError, ProfilesDefinitionError) as error:
            return _invalid(
                revision,
                audit,
                code='access.configuration.invalid',
                message=str(error),
            )
        return DraftValidationResult(
            draft_revision=revision,
            valid=True,
            audit=audit,
            summary=_summary(configuration),
        )


def create_access_manager_module(
    *,
    source: AdaAccessSourceService,
    projection: SourceProjectionService[AdaAccessConfiguration],
    profiles_projection: ProjectionStore[ProfileCatalog],
    profiles_source_key: SourceKey,
    principal_provider: Callable[[], ManagerPrincipal],
    audit_actor_provider: Callable[[], str],
    source_name: str,
    projection_name: str,
) -> ManagerModule:
    source_workflow = AdaAccessManagerSourceWorkflow(
        source=source,
        audit_actor_provider=audit_actor_provider,
    )
    validation_workflow = AdaAccessManagerDraftValidationWorkflow(
        profiles_projection=profiles_projection,
        profiles_source_key=profiles_source_key,
        audit_actor_provider=audit_actor_provider,
    )
    workspace = ManagerWorkspaceBridge(
        owner_subject_id_provider=audit_actor_provider,
        source_snapshot_provider=source.get_current,
    )

    def profiles_provider() -> ProfileCatalog | None:
        active = profiles_projection.get_active(profiles_source_key)
        if active is None or not isinstance(active.payload, ProfileCatalog):
            return None
        return active.payload

    context = AdaAccessAdminWebContext(
        workspace_payload_reader=workspace.read_payload,
        workspace_payload_writer=workspace.write_payload,
        profile_catalog_provider=profiles_provider,
        draft_store_id=workflow_draft_id('access'),
        saved_draft_store_id=workflow_saved_draft_id('access'),
        draft_save_action_id=workflow_action_id('access', 'save-draft'),
        editor_revision_store_id=workflow_editor_revision_id('access'),
        can_manage=lambda: ACCESS_MANAGER_ACCESS_KEY in principal_provider().access_keys,
        source_name=source_name,
        projection_name=projection_name,
    )
    web_module = create_ada_access_admin_web_module(context)

    def register_services(services: ServiceRegistry) -> None:
        services.add(ACCESS_SOURCE_SERVICE, source_workflow)
        services.add(ACCESS_SOURCE_READER_SERVICE, source_workflow)
        services.add(ACCESS_SOURCE_HISTORY_SERVICE, source_workflow)
        services.add(ACCESS_PROJECTION_SERVICE, projection)
        services.add(ACCESS_DRAFT_VALIDATION_SERVICE, validation_workflow)

    web_module = replace(web_module, register_services=register_services)

    return ManagerModule(
        key='access',
        group_key='configuration',
        title='Accesos',
        route='/access',
        order=15,
        description='Definición de accesos y asignación de accesos a perfiles de ADA.',
        layout=lambda _services: build_ada_access_admin_configuration(context),
        source_key=source.source_key,
        source_service=ACCESS_SOURCE_SERVICE,
        source_reader_service=ACCESS_SOURCE_READER_SERVICE,
        source_history_service=ACCESS_SOURCE_HISTORY_SERVICE,
        projection_service=ACCESS_PROJECTION_SERVICE,
        draft_validation_service=ACCESS_DRAFT_VALIDATION_SERVICE,
        access_key=ACCESS_MANAGER_ACCESS_KEY,
        web_module=web_module,
        source_name=source_name,
        projection_name=projection_name,
    )


def _summary(configuration: AdaAccessConfiguration) -> tuple[ProjectionSummaryItem, ...]:
    assignments = sum(len(grant.access_keys) for grant in configuration.profile_access)
    return (
        ProjectionSummaryItem('Accesos definidos', str(len(configuration.access_keys))),
        ProjectionSummaryItem('Perfiles con accesos', str(len(configuration.profile_access))),
        ProjectionSummaryItem('Asignaciones', str(assignments)),
    )


def _audit_actor(provider: Callable[[], str]) -> str:
    actor = provider().strip()
    if not actor:
        raise ValueError('Manager audit actor must not be empty')
    return actor


def _invalid(
    revision: str,
    audit: ProjectionAuditRecord,
    *,
    code: str,
    message: str,
) -> DraftValidationResult:
    return DraftValidationResult(
        draft_revision=revision,
        valid=False,
        audit=audit,
        issues=(ProjectionIssue(code=code, message=message),),
    )
