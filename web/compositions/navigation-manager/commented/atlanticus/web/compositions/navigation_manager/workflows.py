# Espejo pedagógico del archivo productivo; conserva exactamente su comportamiento.
# Los comentarios en español describen responsabilidades sin alterar el contrato ejecutable.
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from atlanticus.web.manager.projection import (
    DraftValidationResult,
    ProjectionAuditRecord,
    ProjectionIssue,
    ProjectionSummaryItem,
)
from atlanticus.web.manager.source import (
    SourceHistoryReadResult,
    SourcePublicationResult,
    SourceReadResult,
)
from atlanticus.web.manager.workspace import build_workspace_revision
from atlanticus.web.navigation.configuration.errors import (
    NavigationConfigurationSourceError,
    NavigationConfigurationValidationError,
)
from atlanticus.web.navigation.configuration.models import NavigationConfigurationCatalog
from atlanticus.web.navigation.configuration.source_release import NavigationSourceService
from atlanticus.web.source.models import HistoryPage, SourceKey, SourceReleaseRef, SourceSnapshot

NavigationAuditActorProvider = Callable[[], str]


# Responsabilidad: NavigationManagerSourceWorkflow encapsula una frontera explícita del contrato vigente.
class NavigationManagerSourceWorkflow:
    # Operación: __init__ mantiene la misma semántica que el código productivo.
    def __init__(
        self,
        *,
        source: NavigationSourceService,
        audit_actor_provider: NavigationAuditActorProvider,
    ) -> None:
        self._source = source
        self._audit_actor_provider = audit_actor_provider

    @property
    # Operación: source_key mantiene la misma semántica que el código productivo.
    def source_key(self) -> SourceKey:
        return self._source.source_key

    # Operación: get_source_snapshot mantiene la misma semántica que el código productivo.
    def get_source_snapshot(self) -> SourceSnapshot:
        return self._source.get_current()

    # Operación: load_current_source mantiene la misma semántica que el código productivo.
    def load_current_source(self) -> SourceReadResult:
        snapshot = self._source.get_current()
        if snapshot.current is None:
            return SourceReadResult(snapshot=snapshot, payload=None)
        release = self._source.load_release(snapshot.current.release_ref)
        refreshed = self._source.get_current()
        if refreshed.current != snapshot.current:
            raise NavigationConfigurationSourceError(
                'Navigation source changed while it was being loaded'
            )
        return SourceReadResult(
            snapshot=refreshed,
            payload=release.catalog.to_document(),
        )

    # Operación: list_history mantiene la misma semántica que el código productivo.
    def list_history(self, *, limit: int = 20) -> HistoryPage:
        return self._source.query_history(page_size=limit)

    # Operación: load_history_release mantiene la misma semántica que el código productivo.
    def load_history_release(
        self,
        release_ref: SourceReleaseRef,
    ) -> SourceHistoryReadResult:
        release = self._source.load_release(release_ref)
        return SourceHistoryReadResult(
            release_ref=release.release_ref,
            payload=release.catalog.to_document(),
        )

    # Operación: publish_draft mantiene la misma semántica que el código productivo.
    def publish_draft(
        self,
        payload: dict[str, object],
        expected_source_snapshot: SourceSnapshot,
    ) -> SourcePublicationResult:
        if expected_source_snapshot.source_key != self._source.source_key:
            raise NavigationConfigurationSourceError(
                'Navigation source snapshot uses a different source key'
            )
        current = self._source.get_current()
        if current.current != expected_source_snapshot.current:
            raise NavigationConfigurationSourceError(
                'Navigation source changed before publication'
            )
        actor = self._audit_actor_provider().strip()
        if not actor:
            raise NavigationConfigurationSourceError(
                'Navigation source publication actor must not be empty'
            )
        catalog = NavigationConfigurationCatalog.from_document(dict(payload))
        basis_release = current.current.release_ref if current.current is not None else None
        published = self._source.publish_catalog(
            catalog,
            published_by=actor,
            expected_concurrency_token=current.concurrency_token,
            basis_release=basis_release,
        )
        return SourcePublicationResult(
            source=published,
            audit=ProjectionAuditRecord(
                actor=actor,
                occurred_at=published.release.release_ref.published_at_utc,
            ),
            summary=_summary(catalog),
        )


# Responsabilidad: NavigationManagerDraftValidationWorkflow encapsula una frontera explícita del contrato vigente.
class NavigationManagerDraftValidationWorkflow:
    # Operación: __init__ mantiene la misma semántica que el código productivo.
    def __init__(self, *, audit_actor_provider: NavigationAuditActorProvider) -> None:
        self._audit_actor_provider = audit_actor_provider

    # Operación: validate_draft mantiene la misma semántica que el código productivo.
    def validate_draft(self, payload: dict[str, object]) -> DraftValidationResult:
        audit = ProjectionAuditRecord(
            actor=self._audit_actor_provider().strip(),
            occurred_at=datetime.now(UTC),
        )
        revision = build_workspace_revision(payload)
        try:
            catalog = NavigationConfigurationCatalog.from_document(dict(payload))
            catalog.to_definition()
        except NavigationConfigurationValidationError as error:
            return DraftValidationResult(
                draft_revision=revision,
                valid=False,
                audit=audit,
                issues=(
                    ProjectionIssue(
                        code='navigation.configuration.invalid',
                        message=str(error),
                    ),
                ),
            )
        return DraftValidationResult(
            draft_revision=revision,
            valid=True,
            audit=audit,
            summary=_summary(catalog),
        )


# Operación: _summary mantiene la misma semántica que el código productivo.
def _summary(
    catalog: NavigationConfigurationCatalog,
) -> tuple[ProjectionSummaryItem, ...]:
    grouped_links = sum(len(group.links) for group in catalog.groups)
    enabled_links = sum(1 for link in catalog.links if link.enabled) + sum(
        1 for group in catalog.groups if group.enabled for link in group.links if link.enabled
    )
    return (
        ProjectionSummaryItem('Enlaces', str(len(catalog.links) + grouped_links)),
        ProjectionSummaryItem('Enlaces habilitados', str(enabled_links)),
        ProjectionSummaryItem('Secciones', str(len(catalog.groups))),
    )
