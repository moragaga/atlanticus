from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from ada.configuration.kpi_definition.authority import KpiDefinitionAuthorityCatalog
from ada.configuration.kpi_definition.contracts import (
    KpiDefinitionAuditActorProvider,
    KpiDefinitionAuthorityProvider,
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


@dataclass(frozen=True, slots=True)
class KpiDefinitionServices:
    administration: KpiDefinitionAdministrationService
    projection_workflow: KpiDefinitionProjectionWorkflow


class KpiDefinitionAdministrationService:
    def __init__(
        self,
        *,
        source: KpiDefinitionSource,
        publisher: KpiDefinitionPublisher,
        authority: KpiDefinitionAuthorityProvider,
        audit_actor_provider: KpiDefinitionAuditActorProvider,
    ) -> None:
        self._source = source
        self._publisher = publisher
        self._authority = authority
        self._audit_actor_provider = audit_actor_provider

    def load_source(self) -> KpiDefinitionSourceDocument | None:
        return self._source.load()

    def load_configuration(self) -> KpiDefinitionConfiguration | None:
        document = self.load_source()
        return document.configuration if document is not None else None

    def list_history(
        self,
        *,
        limit: int = 20,
    ) -> tuple[KpiDefinitionSourceDocument, ...]:
        return self._source.list_history(limit=limit)

    def load_revision_configuration(
        self,
        revision: str,
    ) -> KpiDefinitionConfiguration:
        normalized = revision.strip() if isinstance(revision, str) else ''
        document = self._source.load_revision(normalized) if normalized else None
        if document is None:
            raise KpiDefinitionSourceError('KPI definition revision does not exist')
        return document.configuration

    def validate_configuration(
        self,
        configuration: KpiDefinitionConfiguration,
    ) -> KpiDefinitionValidationResult:
        validated = _require_configuration(configuration)
        authority = self._authority.load()
        issues = _validate_configuration(validated, authority)
        return KpiDefinitionValidationResult(
            draft_revision=build_kpi_definition_digest(validated),
            valid=not any(issue.level == 'error' for issue in issues),
            audit=_audit_record(self._audit_actor_provider),
            kpi_configuration_revision=(
                authority.kpi_configuration_revision if authority is not None else None
            ),
            issues=issues,
            summary=_configuration_summary(validated, authority),
        )

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
        authority = self._require_authority()
        issues = _validate_configuration(validated, authority)
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
        summary = _configuration_summary(validated, authority)
        if current_revision == document.revision:
            return KpiDefinitionPublicationResult(
                source_revision=document.revision,
                published=False,
                audit=audit,
                kpi_configuration_revision=authority.kpi_configuration_revision,
                summary=summary,
            )
        self._require_authority(expected_revision=authority.kpi_configuration_revision)
        self._publisher.publish(
            document,
            expected_revision=expected_source_revision,
        )
        return KpiDefinitionPublicationResult(
            source_revision=document.revision,
            published=True,
            audit=audit,
            kpi_configuration_revision=authority.kpi_configuration_revision,
            summary=summary,
        )

    def _require_authority(
        self,
        *,
        expected_revision: str | None = None,
    ) -> KpiDefinitionAuthorityCatalog:
        authority = self._authority.load()
        if authority is None:
            raise KpiDefinitionValidationError('KPI configuration authority is not available')
        if (
            expected_revision is not None
            and authority.kpi_configuration_revision != expected_revision
        ):
            raise KpiDefinitionValidationError(
                'KPI configuration revision changed before definition publication'
            )
        return authority


class KpiDefinitionProjectionWorkflow:
    def __init__(
        self,
        *,
        source: KpiDefinitionSource,
        projection: KpiDefinitionProjectionRepository,
        authority: KpiDefinitionAuthorityProvider,
        audit_actor_provider: KpiDefinitionAuditActorProvider,
    ) -> None:
        self._source = source
        self._projection = projection
        self._authority = authority
        self._audit_actor_provider = audit_actor_provider

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
            active_source_revision=(active.source_revision if active is not None else None),
            active_kpi_configuration_revision=(
                active.kpi_configuration_revision if active is not None else None
            ),
            projection_audit=(
                KpiDefinitionAuditRecord(
                    actor=active.projected_by,
                    occurred_at_utc=active.projected_at_utc,
                )
                if active is not None
                else None
            ),
        )

    def project(
        self,
        expected_source_revision: str,
    ) -> KpiDefinitionProjectionResult:
        expected = (
            expected_source_revision.strip() if isinstance(expected_source_revision, str) else ''
        )
        if not expected:
            raise KpiDefinitionProjectionError(
                'Expected KPI definition source revision must not be empty'
            )
        source = self._require_source(expected)
        authority = self._require_authority()
        issues = _validate_configuration(source.configuration, authority)
        if any(issue.level == 'error' for issue in issues):
            raise KpiDefinitionProjectionError(
                'Published KPI definition configuration is not valid for projection'
            )
        active = self._projection.load()
        if (
            active is not None
            and active.source_revision == expected
            and active.kpi_configuration_revision == authority.kpi_configuration_revision
        ):
            self._require_source(expected)
            self._require_authority(expected_revision=authority.kpi_configuration_revision)
            return KpiDefinitionProjectionResult(
                source_revision=source.revision,
                projection_revision=active.revision,
                kpi_configuration_revision=active.kpi_configuration_revision,
                projected=False,
                audit=KpiDefinitionAuditRecord(
                    actor=active.projected_by,
                    occurred_at_utc=active.projected_at_utc,
                ),
                issues=issues,
                summary=_configuration_summary(
                    source.configuration,
                    authority,
                ),
            )
        audit = _audit_record(self._audit_actor_provider)
        candidate = KpiDefinitionProjection.create(
            configuration=source.configuration,
            source_revision=source.revision,
            authority=authority,
            projected_by=audit.actor,
            projected_at_utc=audit.occurred_at_utc,
        )
        self._require_source(expected)
        self._require_authority(expected_revision=authority.kpi_configuration_revision)
        saved = self._projection.save(candidate)
        self._require_source(expected)
        self._require_authority(expected_revision=authority.kpi_configuration_revision)
        return KpiDefinitionProjectionResult(
            source_revision=source.revision,
            projection_revision=saved.revision,
            kpi_configuration_revision=saved.kpi_configuration_revision,
            projected=True,
            audit=KpiDefinitionAuditRecord(
                actor=saved.projected_by,
                occurred_at_utc=saved.projected_at_utc,
            ),
            issues=issues,
            summary=_configuration_summary(
                source.configuration,
                authority,
            ),
        )

    def _require_source(
        self,
        expected_revision: str,
    ) -> KpiDefinitionSourceDocument:
        document = self._source.load()
        if document is None:
            raise KpiDefinitionSourceError('KPI definition source does not exist')
        if document.revision != expected_revision:
            raise KpiDefinitionProjectionError(
                'KPI definition source revision changed before projection'
            )
        return document

    def _require_authority(
        self,
        *,
        expected_revision: str | None = None,
    ) -> KpiDefinitionAuthorityCatalog:
        authority = self._authority.load()
        if authority is None:
            raise KpiDefinitionProjectionError('KPI configuration authority is not available')
        if (
            expected_revision is not None
            and authority.kpi_configuration_revision != expected_revision
        ):
            raise KpiDefinitionProjectionError(
                'KPI configuration revision changed before definition projection'
            )
        return authority


def compose_kpi_definition_services(
    *,
    source: KpiDefinitionSource,
    publisher: KpiDefinitionPublisher,
    projection: KpiDefinitionProjectionRepository,
    authority: KpiDefinitionAuthorityProvider,
    audit_actor_provider: KpiDefinitionAuditActorProvider,
) -> KpiDefinitionServices:
    return KpiDefinitionServices(
        administration=KpiDefinitionAdministrationService(
            source=source,
            publisher=publisher,
            authority=authority,
            audit_actor_provider=audit_actor_provider,
        ),
        projection_workflow=KpiDefinitionProjectionWorkflow(
            source=source,
            projection=projection,
            authority=authority,
            audit_actor_provider=audit_actor_provider,
        ),
    )


def _require_configuration(
    configuration: KpiDefinitionConfiguration,
) -> KpiDefinitionConfiguration:
    if not isinstance(configuration, KpiDefinitionConfiguration):
        raise KpiDefinitionValidationError('KPI definition configuration is invalid')
    return configuration


def _validate_configuration(
    configuration: KpiDefinitionConfiguration,
    authority: KpiDefinitionAuthorityCatalog | None,
) -> tuple[KpiDefinitionIssue, ...]:
    _require_configuration(configuration)
    if authority is None:
        return (
            KpiDefinitionIssue(
                code='kpi_definition.authority.missing',
                message='KPI configuration authority is not available',
                path='definitions',
            ),
        )
    defined = {
        definition.kpi_key: index for index, definition in enumerate(configuration.definitions)
    }
    issues: list[KpiDefinitionIssue] = []
    for kpi_key, index in defined.items():
        if kpi_key not in authority.keys:
            issues.append(
                KpiDefinitionIssue(
                    code='kpi_definition.orphan',
                    message=(f'KPI definition {kpi_key!r} does not exist in KPI configuration'),
                    path=f'definitions[{index}].kpi_key',
                )
            )
    for kpi_key in authority.kpi_keys:
        if kpi_key not in defined:
            issues.append(
                KpiDefinitionIssue(
                    code='kpi_definition.missing',
                    message=f'KPI definition {kpi_key!r} is missing',
                    level='warning',
                    path='definitions',
                )
            )
    return tuple(issues)


def _configuration_summary(
    configuration: KpiDefinitionConfiguration,
    authority: KpiDefinitionAuthorityCatalog | None,
) -> tuple[KpiDefinitionSummaryItem, ...]:
    field_count = sum(len(definition.fields) for definition in configuration.definitions)
    if authority is None:
        total = len(configuration.definitions)
        missing = 0
        orphan = 0
    else:
        defined = {definition.kpi_key for definition in configuration.definitions}
        total = len(authority.kpi_keys)
        missing = len(authority.keys - defined)
        orphan = len(defined - authority.keys)
    return (
        KpiDefinitionSummaryItem('KPIs', str(total)),
        KpiDefinitionSummaryItem(
            'Definidos',
            str(len(configuration.definitions) - orphan),
        ),
        KpiDefinitionSummaryItem('Pendientes', str(missing)),
        KpiDefinitionSummaryItem('Huérfanos', str(orphan)),
        KpiDefinitionSummaryItem('Campos', str(field_count)),
    )


def _audit_record(
    provider: KpiDefinitionAuditActorProvider,
) -> KpiDefinitionAuditRecord:
    return KpiDefinitionAuditRecord(
        actor=provider(),
        occurred_at_utc=datetime.now(UTC),
    )
