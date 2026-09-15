from __future__ import annotations

from atlanticus.web.manager.exact_source import ExactSourcePublicationResult
from atlanticus.web.manager.projection import ProjectionAuditRecord
from atlanticus.web.source.models import SourceSnapshot
from atlanticus.web.users.configuration.admin_composition import (
    UsersProfilesAdministrationService,
)
from atlanticus.web.users.configuration.canonical import UsersProfilesConfiguration
from atlanticus.web.users.configuration.contracts import UsersAuditActorProvider


class UsersManagerExactSourceWorkflow:
    def __init__(
        self,
        *,
        administration: UsersProfilesAdministrationService,
        audit_actor_provider: UsersAuditActorProvider,
    ) -> None:
        self._administration = administration
        self._audit_actor_provider = audit_actor_provider

    def get_source_snapshot(self) -> SourceSnapshot:
        return self._administration.get_source_snapshot()

    def publish_draft_exact(
        self,
        payload: dict[str, object],
        expected_source_snapshot: SourceSnapshot,
    ) -> ExactSourcePublicationResult:
        configuration = UsersProfilesConfiguration.from_document(dict(payload))
        actor = self._audit_actor_provider().strip()
        published = self._administration.publish(
            configuration,
            expected_source_snapshot=expected_source_snapshot,
            published_by=actor,
        )
        return ExactSourcePublicationResult(
            source=published,
            audit=ProjectionAuditRecord(
                actor=actor,
                occurred_at=published.release.release_ref.published_at_utc,
            ),
        )


def create_users_manager_exact_source_workflow(
    *,
    administration: UsersProfilesAdministrationService,
    audit_actor_provider: UsersAuditActorProvider,
) -> UsersManagerExactSourceWorkflow:
    return UsersManagerExactSourceWorkflow(
        administration=administration,
        audit_actor_provider=audit_actor_provider,
    )
