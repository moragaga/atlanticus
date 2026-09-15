from __future__ import annotations

from datetime import UTC, datetime

from atlanticus.web.manager import (
    DraftValidationResult,
    ExactSourceReadResult,
    ProjectionAuditRecord,
    ProjectionIssue,
    ProjectionSummaryItem,
    build_workspace_revision,
)
from atlanticus.web.users.configuration.admin_composition import (
    UsersProfilesAdministrationService,
)
from atlanticus.web.users.configuration.canonical import UsersProfilesConfiguration
from atlanticus.web.users.configuration.contracts import UsersAuditActorProvider
from atlanticus.web.users.configuration.errors import UsersConfigurationValidationError


class UsersManagerDraftValidationWorkflow:
    def __init__(self, *, audit_actor_provider: UsersAuditActorProvider) -> None:
        self._audit_actor_provider = audit_actor_provider

    def validate_draft(self, payload: dict[str, object]) -> DraftValidationResult:
        audit = ProjectionAuditRecord(
            actor=self._audit_actor_provider().strip(),
            occurred_at=datetime.now(UTC),
        )
        revision = build_workspace_revision(payload)
        try:
            configuration = UsersProfilesConfiguration.from_document(dict(payload))
        except UsersConfigurationValidationError as error:
            return DraftValidationResult(
                draft_revision=revision,
                valid=False,
                audit=audit,
                issues=(
                    ProjectionIssue(
                        code='users.configuration.invalid',
                        message=str(error),
                    ),
                ),
            )
        enabled = sum(1 for user in configuration.users.users if user.enabled)
        functional_profiles = sum(
            1 for profile in configuration.profiles.profiles if profile.key != 'administrator'
        )
        return DraftValidationResult(
            draft_revision=revision,
            valid=True,
            audit=audit,
            summary=(
                ProjectionSummaryItem('Usuarios', str(len(configuration.users.users))),
                ProjectionSummaryItem('Usuarios activos', str(enabled)),
                ProjectionSummaryItem('Perfiles funcionales', str(functional_profiles)),
            ),
        )


class UsersManagerExactSourceReaderWorkflow:
    def __init__(self, *, administration: UsersProfilesAdministrationService) -> None:
        self._administration = administration

    def load_current_source_exact(self) -> ExactSourceReadResult:
        state = self._administration.load_current()
        return ExactSourceReadResult(
            snapshot=state.source_snapshot,
            payload=(
                state.configuration.to_document()
                if state.configuration is not None
                else None
            ),
        )


def create_users_manager_draft_validation_workflow(
    *,
    audit_actor_provider: UsersAuditActorProvider,
) -> UsersManagerDraftValidationWorkflow:
    return UsersManagerDraftValidationWorkflow(
        audit_actor_provider=audit_actor_provider,
    )


def create_users_manager_exact_source_reader_workflow(
    *,
    administration: UsersProfilesAdministrationService,
) -> UsersManagerExactSourceReaderWorkflow:
    return UsersManagerExactSourceReaderWorkflow(
        administration=administration,
    )
