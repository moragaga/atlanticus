from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from ada.configuration.kpi_definition.contracts import (
    KpiDefinitionAuditActorProvider,
    KpiDefinitionProjectionRepository,
    KpiDefinitionPublisher,
    KpiDefinitionSource,
)
from ada.configuration.kpi_definition.errors import (
    KpiDefinitionProjectionError,
    KpiDefinitionSourceError,
    KpiDefinitionValidationError,
)
from ada.configuration.kpi_definition.lifecycle import (
    KpiDefinitionAuditRecord,
    KpiDefinitionIssue,
    KpiDefinitionProjectionResult,
    KpiDefinitionPublicationResult,
    KpiDefinitionStatus,
    KpiDefinitionSummaryItem,
    KpiDefinitionValidationResult,
)
from ada.configuration.kpi_definition.models import KpiDefinitionConfiguration
from ada.configuration.kpi_definition.projection import KpiDefinitionProjection
from ada.configuration.kpi_definition.source import (
    KpiDefinitionSourceDocument,
    build_kpi_definition_digest,
)


# Agrupa los dos servicios del dominio sin crear un cliente global.
@dataclass(frozen=True, slots=True)
class KpiDefinitionServices:
    administration: KpiDefinitionAdministrationService
    projection_workflow: KpiDefinitionProjectionWorkflow


# Administra validación y publicación de la fuente autoritativa.
class KpiDefinitionAdministrationService:
    def __init__(
        self,
        *,
        source: KpiDefinitionSource,
        publisher: KpiDefinitionPublisher,
        audit_actor_provider: KpiDefinitionAuditActorProvider,
    ) -> None:
        self._source = source
        self._publisher = publisher
        self._audit_actor_provider = audit_actor_provider

    # Lee el documento fuente sin asumir SharePoint, File u otro adaptador.
    def load_source(self) -> KpiDefinitionSourceDocument | None:
        return self._source.load()

    # Expone sólo la configuración cuando el consumidor no necesita metadata.
    def load_configuration(self) -> KpiDefinitionConfiguration | None:
        document = self.load_source()
        return document.configuration if document is not None else None

    # Delega el orden y límite del historial a la implementación de Source.
    def list_history(
        self,
        *,
        limit: int = 20,
    ) -> tuple[KpiDefinitionSourceDocument, ...]:
        return self._source.list_history(limit=limit)

    # Recupera una revisión histórica como configuración editable del dominio.
    def load_revision_configuration(
        self,
        revision: str,
    ) -> KpiDefinitionConfiguration:
        normalized = revision.strip() if isinstance(revision, str) else ''
        document = self._source.load_revision(normalized) if normalized else None
        if document is None:
            raise KpiDefinitionSourceError('KPI definition revision does not exist')
        return document.configuration

    # Valida el modelo tipado y entrega revision, auditoría y resumen.
    def validate_configuration(
        self,
        configuration: KpiDefinitionConfiguration,
    ) -> KpiDefinitionValidationResult:
        validated = _require_configuration(configuration)
        audit = _audit_record(self._audit_actor_provider)
        issues = _validate_configuration(validated)
        return KpiDefinitionValidationResult(
            draft_revision=build_kpi_definition_digest(validated),
            valid=not any(issue.level == 'error' for issue in issues),
            audit=audit,
            issues=issues,
            summary=_configuration_summary(validated),
        )

    # Verifica CAS antes de publicar y evita escribir contenido idéntico.
    def publish_configuration(
        self,
        configuration: KpiDefinitionConfiguration,
        *,
        expected_source_revision: str | None,
    ) -> KpiDefinitionPublicationResult:
        validated = _require_configuration(configuration)
        current = self._source.load()
        current_revision = current.revision if current is not None else None
        if current_revision != expected_source_revision:
            raise KpiDefinitionSourceError(
                'KPI definition source revision changed before publication'
            )
        issues = _validate_configuration(validated)
        if any(issue.level == 'error' for issue in issues):
            raise KpiDefinitionValidationError(
                'KPI definition configuration must be valid before publication'
            )
        audit = _audit_record(self._audit_actor_provider)
        document = KpiDefinitionSourceDocument.create(
            configuration=validated,
            saved_by=audit.actor,
            saved_at_utc=audit.occurred_at_utc,
        )
        summary = _configuration_summary(validated)
        if current_revision == document.revision:
            return KpiDefinitionPublicationResult(
                source_revision=document.revision,
                published=False,
                audit=audit,
                summary=summary,
            )
        self._publisher.publish(
            document,
            expected_revision=expected_source_revision,
        )
        return KpiDefinitionPublicationResult(
            source_revision=document.revision,
            published=True,
            audit=audit,
            summary=summary,
        )


# Mantiene el estado Source/Projection y ejecuta la proyección con control de carrera.
class KpiDefinitionProjectionWorkflow:
    def __init__(
        self,
        *,
        source: KpiDefinitionSource,
        projection: KpiDefinitionProjectionRepository,
        audit_actor_provider: KpiDefinitionAuditActorProvider,
    ) -> None:
        self._source = source
        self._projection = projection
        self._audit_actor_provider = audit_actor_provider

    # Construye el status sin conocer al Manager.
    def get_status(self) -> KpiDefinitionStatus:
        source = self._source.load()
        active = self._projection.load()
        return KpiDefinitionStatus(
            source_revision=source.revision if source is not None else None,
            source_audit=(
                KpiDefinitionAuditRecord(
                    actor=source.saved_by,
                    occurred_at_utc=source.saved_at_utc,
                )
                if source is not None
                else None
            ),
            active_revision=active.revision if active is not None else None,
            active_source_revision=active.source_revision if active is not None else None,
            projection_audit=(
                KpiDefinitionAuditRecord(
                    actor=active.projected_by,
                    occurred_at_utc=active.projected_at_utc,
                )
                if active is not None
                else None
            ),
        )

    # Proyecta sólo la revisión esperada y evita reescribir una proyección sincronizada.
    def project(self, expected_source_revision: str) -> KpiDefinitionProjectionResult:
        expected = (
            expected_source_revision.strip() if isinstance(expected_source_revision, str) else ''
        )
        if not expected:
            raise KpiDefinitionProjectionError(
                'Expected KPI definition source revision must not be empty'
            )
        source = self._require_source(expected)
        issues = _validate_configuration(source.configuration)
        if any(issue.level == 'error' for issue in issues):
            raise KpiDefinitionProjectionError(
                'Published KPI definition configuration is not valid for projection'
            )
        active = self._projection.load()
        if active is not None and active.source_revision == expected:
            self._require_source(expected)
            return KpiDefinitionProjectionResult(
                source_revision=source.revision,
                projection_revision=active.revision,
                projected=False,
                audit=KpiDefinitionAuditRecord(
                    actor=active.projected_by,
                    occurred_at_utc=active.projected_at_utc,
                ),
                issues=issues,
                summary=_configuration_summary(source.configuration),
            )
        audit = _audit_record(self._audit_actor_provider)
        projection = KpiDefinitionProjection.create(
            configuration=source.configuration,
            source_revision=source.revision,
            projected_by=audit.actor,
            projected_at_utc=audit.occurred_at_utc,
        )
        self._require_source(expected)
        saved = self._projection.save(projection)
        self._require_source(expected)
        return KpiDefinitionProjectionResult(
            source_revision=source.revision,
            projection_revision=saved.revision,
            projected=True,
            audit=KpiDefinitionAuditRecord(
                actor=saved.projected_by,
                occurred_at_utc=saved.projected_at_utc,
            ),
            issues=issues,
            summary=_configuration_summary(source.configuration),
        )

    # Relee Source para detectar cambios antes o durante la proyección.
    def _require_source(self, expected_revision: str) -> KpiDefinitionSourceDocument:
        document = self._source.load()
        if document is None:
            raise KpiDefinitionSourceError('KPI definition source does not exist')
        if document.revision != expected_revision:
            raise KpiDefinitionProjectionError(
                'KPI definition source revision changed before projection'
            )
        return document


# Compone explícitamente servicios desde contratos inyectados.
def compose_kpi_definition_services(
    *,
    source: KpiDefinitionSource,
    publisher: KpiDefinitionPublisher,
    projection: KpiDefinitionProjectionRepository,
    audit_actor_provider: KpiDefinitionAuditActorProvider,
) -> KpiDefinitionServices:
    return KpiDefinitionServices(
        administration=KpiDefinitionAdministrationService(
            source=source,
            publisher=publisher,
            audit_actor_provider=audit_actor_provider,
        ),
        projection_workflow=KpiDefinitionProjectionWorkflow(
            source=source,
            projection=projection,
            audit_actor_provider=audit_actor_provider,
        ),
    )


# Protege la frontera tipada antes de operar sobre la configuración.
def _require_configuration(
    configuration: KpiDefinitionConfiguration,
) -> KpiDefinitionConfiguration:
    if not isinstance(configuration, KpiDefinitionConfiguration):
        raise KpiDefinitionValidationError('KPI definition configuration is invalid')
    return configuration


# Reserva una única frontera para reglas intrínsecas adicionales futuras.
def _validate_configuration(
    configuration: KpiDefinitionConfiguration,
) -> tuple[KpiDefinitionIssue, ...]:
    _require_configuration(configuration)
    return ()


# Resume cantidad de KPI y campos descriptivos sin imponer presentación.
def _configuration_summary(
    configuration: KpiDefinitionConfiguration,
) -> tuple[KpiDefinitionSummaryItem, ...]:
    field_count = sum(len(definition.fields) for definition in configuration.definitions)
    return (
        KpiDefinitionSummaryItem('KPIs', str(len(configuration.definitions))),
        KpiDefinitionSummaryItem('Campos', str(field_count)),
    )


# Obtiene actor desde composición y genera timestamp UTC para la operación.
def _audit_record(
    provider: KpiDefinitionAuditActorProvider,
) -> KpiDefinitionAuditRecord:
    return KpiDefinitionAuditRecord(
        actor=provider(),
        occurred_at_utc=datetime.now(UTC),
    )
