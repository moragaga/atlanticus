from __future__ import annotations

from atlanticus.web.manager.exact_source import ExactSourcePublicationResult
from atlanticus.web.manager.projection import ProjectionAuditRecord
from atlanticus.web.source.models import SourceSnapshot
from atlanticus.web.users.configuration.admin_composition import (
    UsersProfilesAdministrationService,
)
from atlanticus.web.users.configuration.canonical import UsersProfilesConfiguration
from atlanticus.web.users.configuration.contracts import UsersAuditActorProvider


# Esta composición vive fuera de Manager y de Users para conservar ambas capacidades independientes.
# Su única responsabilidad es adaptar el backend administrativo de Users al protocolo exact-source.
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
        # Manager recibe el value object exacto; no se degrada release ni token a texto.
        return self._administration.get_source_snapshot()

    def publish_draft_exact(
        self,
        payload: dict[str, object],
        expected_source_snapshot: SourceSnapshot,
    ) -> ExactSourcePublicationResult:
        # El payload cruza la frontera como documento y se valida de nuevo con el contrato canónico Users.
        configuration = UsersProfilesConfiguration.from_document(dict(payload))
        actor = self._audit_actor_provider().strip()
        # La administración de Users conserva la responsabilidad del precheck de dominio y entrega
        # a Source el ConcurrencyToken y basis_release correspondientes al snapshot observado.
        published = self._administration.publish(
            configuration,
            expected_source_snapshot=expected_source_snapshot,
            published_by=actor,
        )
        # El timestamp de auditoría se toma de la release que Source confirmó como publicada.
        # No se crea un segundo reloj ni se rebasa aquí ningún draft de sesión.
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
    # Factory mínima para composition roots: no registra servicios ni conoce la aplicación host.
    return UsersManagerExactSourceWorkflow(
        administration=administration,
        audit_actor_provider=audit_actor_provider,
    )
