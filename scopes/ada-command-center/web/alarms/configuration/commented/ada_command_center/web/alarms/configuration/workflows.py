# Este módulo adapta Alarm Configuration a los workflows genéricos de Manager.
# La validación es intrínseca y reutiliza AlarmConfiguration.from_document como autoridad.
# Publicar conserva SourceSnapshot/concurrencia y la historia lee releases exactas.
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from ada_command_center.domain.alarms import (
    AlarmConfiguration,
    AlarmConfigurationValidationError,
)
from ada_command_center.web.alarms.configuration.errors import AlarmConfigurationSourceError
from ada_command_center.web.alarms.configuration.source_release import (
    AlarmConfigurationSourceService,
)
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
from atlanticus.web.source.models import HistoryPage, SourceKey, SourceReleaseRef, SourceSnapshot

AlarmConfigurationAuditActorProvider = Callable[[], str]


class AlarmConfigurationManagerSourceWorkflow:
    def __init__(
        self,
        *,
        source: AlarmConfigurationSourceService,
        audit_actor_provider: AlarmConfigurationAuditActorProvider,
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
        refreshed = self._source.get_current()
        if refreshed.current != snapshot.current:
            raise AlarmConfigurationSourceError(
                'Alarm Configuration source changed while it was being loaded'
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
            raise AlarmConfigurationSourceError(
                'Alarm Configuration source snapshot uses a different source key'
            )
        current = self._source.get_current()
        if current.current != expected_source_snapshot.current:
            raise AlarmConfigurationSourceError(
                'Alarm Configuration source changed before publication'
            )
        actor = self._audit_actor_provider().strip()
        if not actor:
            raise AlarmConfigurationSourceError(
                'Alarm Configuration publication actor must not be empty'
            )
        configuration = AlarmConfiguration.from_document(dict(payload))
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


class AlarmConfigurationManagerDraftValidationWorkflow:
    def __init__(
        self,
        *,
        audit_actor_provider: AlarmConfigurationAuditActorProvider,
    ) -> None:
        self._audit_actor_provider = audit_actor_provider

    def validate_draft(self, payload: dict[str, object]) -> DraftValidationResult:
        audit = ProjectionAuditRecord(
            actor=self._audit_actor_provider().strip(),
            occurred_at=datetime.now(UTC),
        )
        revision = build_workspace_revision(payload)
        try:
            configuration = AlarmConfiguration.from_document(dict(payload))
        except AlarmConfigurationValidationError as error:
            return DraftValidationResult(
                draft_revision=revision,
                valid=False,
                audit=audit,
                issues=(
                    ProjectionIssue(
                        code='alarm.configuration.invalid',
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
    configuration: AlarmConfiguration,
) -> tuple[ProjectionSummaryItem, ...]:
    return (
        ProjectionSummaryItem('Rules', str(len(configuration.rules))),
        ProjectionSummaryItem(
            'Active rules',
            str(sum(rule.is_active for rule in configuration.rules)),
        ),
        ProjectionSummaryItem('Messages', str(len(configuration.messages))),
    )
