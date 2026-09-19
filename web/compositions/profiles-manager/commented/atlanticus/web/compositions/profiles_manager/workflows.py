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
from atlanticus.web.profiles.configuration.errors import ProfilesConfigurationSourceError
from atlanticus.web.profiles.configuration.models import ProfilesConfiguration
from atlanticus.web.profiles.configuration.source_release import ProfilesSourceService
from atlanticus.web.profiles.errors import ProfilesDefinitionError
from atlanticus.web.source.models import HistoryPage, SourceKey, SourceReleaseRef, SourceSnapshot

ProfilesAuditActorProvider = Callable[[], str]


# Adapta el lifecycle durable de Profiles al contrato genérico que Manager espera para Source.
class ProfilesManagerSourceWorkflow:
    def __init__(
        self,
        *,
        source: ProfilesSourceService,
        audit_actor_provider: ProfilesAuditActorProvider,
    ) -> None:
        self._source = source
        self._audit_actor_provider = audit_actor_provider

    @property
    def source_key(self) -> SourceKey:
        return self._source.source_key

    def get_source_snapshot(self) -> SourceSnapshot:
        return self._source.get_current()

    def load_current_source(self) -> SourceReadResult:
        snapshot = self._source.get_current()
        if snapshot.current is None:
            return SourceReadResult(snapshot=snapshot, payload=None)
        release = self._source.load_release(snapshot.current.release_ref)
        # Se relee el snapshot para detectar un cambio concurrente durante la carga del release.
        refreshed = self._source.get_current()
        if refreshed.current != snapshot.current:
            raise ProfilesConfigurationSourceError(
                'Profiles source changed while it was being loaded'
            )
        return SourceReadResult(
            snapshot=refreshed,
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
            release_ref=release.release_ref,
            payload=release.configuration.to_document(),
        )

    def publish_draft(
        self,
        payload: dict[str, object],
        expected_source_snapshot: SourceSnapshot,
    ) -> SourcePublicationResult:
        if expected_source_snapshot.source_key != self._source.source_key:
            raise ProfilesConfigurationSourceError(
                'Profiles source snapshot uses a different source key'
            )
        current = self._source.get_current()
        if current.current != expected_source_snapshot.current:
            raise ProfilesConfigurationSourceError('Profiles source changed before publication')
        actor = self._audit_actor_provider().strip()
        if not actor:
            raise ProfilesConfigurationSourceError(
                'Profiles source publication actor must not be empty'
            )
        # El draft se reconstruye por el modelo de dominio antes de tocar Source.
        configuration = ProfilesConfiguration.from_document(dict(payload))
        basis_release = current.current.release_ref if current.current is not None else None
        published = self._source.publish_configuration(
            configuration,
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
            summary=_summary(configuration),
        )


# Manager valida el documento editable con el mismo contrato que luego se publicará.
class ProfilesManagerDraftValidationWorkflow:
    def __init__(
        self,
        *,
        audit_actor_provider: ProfilesAuditActorProvider,
    ) -> None:
        self._audit_actor_provider = audit_actor_provider

    def validate_draft(self, payload: dict[str, object]) -> DraftValidationResult:
        audit = ProjectionAuditRecord(
            actor=self._audit_actor_provider().strip(),
            occurred_at=datetime.now(UTC),
        )
        revision = build_workspace_revision(payload)
        try:
            configuration = ProfilesConfiguration.from_document(dict(payload))
        except ProfilesDefinitionError as error:
            return DraftValidationResult(
                draft_revision=revision,
                valid=False,
                audit=audit,
                issues=(
                    ProjectionIssue(
                        code='profiles.configuration.invalid',
                        message=str(error),
                    ),
                ),
            )
        return DraftValidationResult(
            draft_revision=revision,
            valid=True,
            audit=audit,
            summary=_summary(configuration),
        )


def _summary(
    configuration: ProfilesConfiguration,
) -> tuple[ProjectionSummaryItem, ...]:
    # El total efectivo incluye los cuatro perfiles de sistema más los configurados publicados.
    return (
        ProjectionSummaryItem('Perfiles configurados', str(len(configuration.profiles))),
        ProjectionSummaryItem('Perfiles efectivos', str(len(configuration.catalog().all()))),
    )
