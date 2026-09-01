from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from atlanticus.web.users.configuration.bundle import UsersConfigurationBundle
from atlanticus.web.users.configuration.contracts import (
    DiscoveredUsersSource,
    UsersAuditActorProvider,
    UsersConfigurationPublisher,
    UsersConfigurationSource,
    UsersProjectionRepository,
)
from atlanticus.web.users.configuration.errors import (
    UsersConfigurationProjectionError,
    UsersConfigurationSourceError,
)
from atlanticus.web.users.configuration.models import (
    DiscoveredUser,
    UserConfiguration,
    UsersConfigurationCatalog,
)
from atlanticus.web.users.configuration.projection import (
    UsersAuditRecord,
    UsersDraftValidationResult,
    UsersProjectionExecutionResult,
    UsersProjectionIssue,
    UsersProjectionStatus,
    UsersProjectionSummaryItem,
    UsersSourcePublicationResult,
)


@dataclass(frozen=True, slots=True)
class UsersConfigurationServices:
    administration: UsersAdministrationService
    projection_workflow: UsersProjectionWorkflow
    discovered: DiscoveredUsersSource
    projection: UsersProjectionRepository


class UsersAdministrationService:
    def __init__(
        self,
        *,
        source: UsersConfigurationSource,
        publisher: UsersConfigurationPublisher,
        discovered: DiscoveredUsersSource,
        audit_actor_provider: UsersAuditActorProvider,
    ) -> None:
        self._source = source
        self._publisher = publisher
        self._discovered = discovered
        self._audit_actor_provider = audit_actor_provider

    def load_source(self) -> UsersConfigurationBundle | None:
        return self._source.fetch_bundle()

    def load_catalog(self) -> UsersConfigurationCatalog | None:
        bundle = self.load_source()
        return bundle.catalog if bundle is not None else None

    def list_discovered(self) -> tuple[DiscoveredUser, ...]:
        configured = self.load_catalog()
        configured_users = configured.users if configured else ()
        return tuple(
            user
            for user in self._discovered.list_discovered()
            if not any(_matches_configured_identity(user, current) for current in configured_users)
        )

    def validate_catalog(self, catalog: UsersConfigurationCatalog) -> UsersDraftValidationResult:
        audit = UsersAuditRecord(
            actor=self._audit_actor_provider(),
            occurred_at_utc=datetime.now(UTC),
        )
        issues = _validate_catalog(catalog)
        return UsersDraftValidationResult(
            draft_revision=_build_draft_revision(catalog),
            valid=not any(issue.level == 'error' for issue in issues),
            audit=audit,
            issues=issues,
            summary=_catalog_summary(catalog),
        )

    def publish_catalog(
        self,
        catalog: UsersConfigurationCatalog,
        *,
        expected_source_revision: str | None,
    ) -> UsersSourcePublicationResult:
        validation = self.validate_catalog(catalog)
        if not validation.valid:
            raise UsersConfigurationSourceError('Users draft is not valid for publication')
        current = self._source.fetch_bundle()
        current_revision = current.revision if current is not None else None
        if current_revision != expected_source_revision:
            raise UsersConfigurationSourceError('Users source revision changed before publication')
        bundle = UsersConfigurationBundle.create(
            catalog=catalog,
            saved_by=validation.audit.actor,
            now_utc=validation.audit.occurred_at_utc,
        )
        published = current_revision != bundle.revision
        self._publisher.publish_bundle(
            bundle,
            expected_source_revision=expected_source_revision,
        )
        return UsersSourcePublicationResult(
            source_revision=bundle.revision,
            published=published,
            audit=validation.audit,
            summary=validation.summary,
        )

    def list_history(self, *, limit: int = 20) -> tuple[UsersConfigurationBundle, ...]:
        return self._source.list_history(limit=limit)

    def load_revision_catalog(self, revision: str) -> UsersConfigurationCatalog:
        bundle = self._source.fetch_revision(revision)
        if bundle is None:
            raise UsersConfigurationSourceError('Users configuration revision does not exist')
        return bundle.catalog


class UsersProjectionWorkflow:
    def __init__(
        self,
        *,
        source: UsersConfigurationSource,
        projection: UsersProjectionRepository,
        audit_actor_provider: UsersAuditActorProvider,
    ) -> None:
        self._source = source
        self._projection = projection
        self._audit_actor_provider = audit_actor_provider

    def get_status(self) -> UsersProjectionStatus:
        bundle = self._source.fetch_bundle()
        state = self._projection.load_state()
        return UsersProjectionStatus(
            source_revision=bundle.revision if bundle is not None else None,
            source_audit=(
                UsersAuditRecord(actor=bundle.saved_by, occurred_at_utc=bundle.saved_at_utc)
                if bundle is not None
                else None
            ),
            active_revision=state.revision if state is not None else None,
            active_source_revision=state.source_revision if state is not None else None,
            projection_audit=(
                UsersAuditRecord(
                    actor=state.projected_by,
                    occurred_at_utc=state.projected_at_utc,
                )
                if state is not None
                else None
            ),
        )

    def project(self, expected_source_revision: str) -> UsersProjectionExecutionResult:
        expected = expected_source_revision.strip()
        if not expected:
            raise UsersConfigurationProjectionError(
                'Expected users source revision must not be empty'
            )
        bundle = self._require_source(expected)
        issues = _validate_catalog(bundle.catalog)
        if any(issue.level == 'error' for issue in issues):
            raise UsersConfigurationProjectionError(
                'Published users configuration is not valid for projection'
            )
        actor = self._audit_actor_provider()
        self._require_source(expected)
        state = self._projection.project(bundle, actor=actor)
        self._require_source(expected)
        return UsersProjectionExecutionResult(
            source_revision=bundle.revision,
            projection_revision=state.revision,
            projected=True,
            audit=UsersAuditRecord(
                actor=state.projected_by,
                occurred_at_utc=state.projected_at_utc,
            ),
            summary=_catalog_summary(bundle.catalog),
        )

    def _require_source(self, expected_revision: str) -> UsersConfigurationBundle:
        bundle = self._source.fetch_bundle()
        if bundle is None:
            raise UsersConfigurationSourceError('Users configuration source does not exist')
        if bundle.revision != expected_revision:
            raise UsersConfigurationProjectionError(
                'Users source revision changed before projection'
            )
        return bundle


def compose_users_configuration_services(
    *,
    source: UsersConfigurationSource,
    publisher: UsersConfigurationPublisher,
    projection: UsersProjectionRepository,
    discovered: DiscoveredUsersSource,
    audit_actor_provider: UsersAuditActorProvider,
) -> UsersConfigurationServices:
    return UsersConfigurationServices(
        administration=UsersAdministrationService(
            source=source,
            publisher=publisher,
            discovered=discovered,
            audit_actor_provider=audit_actor_provider,
        ),
        projection_workflow=UsersProjectionWorkflow(
            source=source,
            projection=projection,
            audit_actor_provider=audit_actor_provider,
        ),
        discovered=discovered,
        projection=projection,
    )


def _validate_catalog(
    catalog: UsersConfigurationCatalog,
) -> tuple[UsersProjectionIssue, ...]:
    issues: list[UsersProjectionIssue] = []
    profile_keys = {profile.key for profile in catalog.profile_catalog().all()}
    for index, user in enumerate(catalog.users):
        if user.profile_key not in profile_keys:
            issues.append(
                UsersProjectionIssue(
                    code='user.profile.invalid',
                    message='User profile does not exist',
                    path=f'users[{index}].profile_key',
                )
            )
    return tuple(issues)


def _catalog_summary(
    catalog: UsersConfigurationCatalog,
) -> tuple[UsersProjectionSummaryItem, ...]:
    enabled = sum(1 for user in catalog.users if user.enabled)
    return (
        UsersProjectionSummaryItem('Usuarios', str(len(catalog.users))),
        UsersProjectionSummaryItem('Usuarios activos', str(enabled)),
        UsersProjectionSummaryItem('Perfiles personalizados', str(len(catalog.profiles))),
    )


def _build_draft_revision(catalog: UsersConfigurationCatalog) -> str:
    canonical = json.dumps(
        catalog.to_document(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return hashlib.sha256(canonical).hexdigest()


def _matches_configured_identity(
    discovered: DiscoveredUser,
    configured: UserConfiguration,
) -> bool:
    if discovered.user_id == configured.user_id:
        return True
    if configured.issuer is None or configured.subject_id is None:
        return False
    return (
        discovered.issuer.casefold() == configured.issuer.casefold()
        and discovered.subject_id == configured.subject_id
    )
