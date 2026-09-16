# Compone Users sobre los contratos genéricos CURRENT de Manager.
# La composición conserva sólo la traducción propia del dominio Users/Profiles.
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from atlanticus.web.manager import (
    DraftValidationResult,
    ProjectionAuditRecord,
    ProjectionIssue,
    ProjectionSummaryItem,
    SourceHistoryReadResult,
    SourcePublicationResult,
    SourceReadResult,
    build_workspace_revision,
)
from atlanticus.web.source.models import HistoryPage, SourceReleaseRef, SourceSnapshot
from atlanticus.web.users.configuration.admin_composition import (
    UsersProfilesAdministrationService,
)
from atlanticus.web.users.configuration.canonical import UsersProfilesConfiguration
from atlanticus.web.users.configuration.errors import UsersConfigurationValidationError


# Un solo workflow implementa lectura, historial y publicación del contrato genérico.
class UsersManagerSourceWorkflow:
    def __init__(
        self,
        *,
        administration: UsersProfilesAdministrationService,
        audit_actor_provider: Callable[[], str],
    ) -> None:
        self._administration = administration
        self._audit_actor_provider = audit_actor_provider

    # Devuelve el value object original para preservar token, release y source key.
    def get_source_snapshot(self) -> SourceSnapshot:
        return self._administration.get_source_snapshot()

    # load_current() ya protege contra cambios de source durante la lectura.
    def load_current_source(self) -> SourceReadResult:
        state = self._administration.load_current()
        return SourceReadResult(
            snapshot=state.source_snapshot,
            payload=(
                state.configuration.to_document()
                if state.configuration is not None
                else None
            ),
        )

    # Manager expresa el límite; Users lo traduce al page_size de su servicio.
    def list_history(self, *, limit: int = 20) -> HistoryPage:
        return self._administration.query_history(page_size=limit)

    # La release histórica se expone como el DTO genérico de Manager.
    def load_history_release(
        self,
        release_ref: SourceReleaseRef,
    ) -> SourceHistoryReadResult:
        configuration = self._administration.load_history_release(release_ref)
        return SourceHistoryReadResult(
            release_ref=release_ref,
            payload=configuration.to_document(),
        )

    # La frontera canónica valida el payload antes de llegar a publicación.
    def publish_draft(
        self,
        payload: dict[str, object],
        expected_source_snapshot: SourceSnapshot,
    ) -> SourcePublicationResult:
        configuration = UsersProfilesConfiguration.from_document(dict(payload))
        actor = self._audit_actor_provider().strip()
        published = self._administration.publish(
            configuration,
            expected_source_snapshot=expected_source_snapshot,
            published_by=actor,
        )
        return SourcePublicationResult(
            source=published,
            audit=ProjectionAuditRecord(
                actor=actor,
                occurred_at=published.release.release_ref.published_at_utc,
            ),
        )


# La validación de draft es una capability distinta de publicar o proyectar.
class UsersManagerDraftValidationWorkflow:
    def __init__(self, *, audit_actor_provider: Callable[[], str]) -> None:
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
        return DraftValidationResult(
            draft_revision=revision,
            valid=True,
            audit=audit,
            summary=_summary(configuration),
        )


# Factory explícita para la composición del source de Users.
def create_users_manager_source_workflow(
    *,
    administration: UsersProfilesAdministrationService,
    audit_actor_provider: Callable[[], str],
) -> UsersManagerSourceWorkflow:
    return UsersManagerSourceWorkflow(
        administration=administration,
        audit_actor_provider=audit_actor_provider,
    )


# Factory explícita para la validación del editor de Users.
def create_users_manager_draft_validation_workflow(
    *,
    audit_actor_provider: Callable[[], str],
) -> UsersManagerDraftValidationWorkflow:
    return UsersManagerDraftValidationWorkflow(
        audit_actor_provider=audit_actor_provider,
    )


# El resumen pertenece a la validación del draft; la publicación conserva su resultado actual.
def _summary(
    configuration: UsersProfilesConfiguration,
) -> tuple[ProjectionSummaryItem, ...]:
    enabled = sum(1 for user in configuration.users.users if user.enabled)
    functional_profiles = sum(
        1 for profile in configuration.profiles.profiles if profile.key != 'administrator'
    )
    return (
        ProjectionSummaryItem('Usuarios', str(len(configuration.users.users))),
        ProjectionSummaryItem('Usuarios activos', str(enabled)),
        ProjectionSummaryItem('Perfiles funcionales', str(functional_profiles)),
    )
