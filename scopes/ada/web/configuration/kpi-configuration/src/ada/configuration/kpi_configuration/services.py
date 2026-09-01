from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from ada.configuration.kpi_configuration.contracts import (
    KpiConfigurationAuditActorProvider,
    KpiConfigurationProjectionRepository,
    KpiConfigurationPublisher,
    KpiConfigurationSource,
    KpiDestinationCatalogProvider,
)
from ada.configuration.kpi_configuration.destinations import KpiDestinationCatalog
from ada.configuration.kpi_configuration.errors import (
    KpiConfigurationProjectionError,
    KpiConfigurationSourceError,
    KpiConfigurationValidationError,
)
from ada.configuration.kpi_configuration.lifecycle import (
    KpiConfigurationAuditRecord,
    KpiConfigurationIssue,
    KpiConfigurationProjectionResult,
    KpiConfigurationPublicationResult,
    KpiConfigurationStatus,
    KpiConfigurationSummaryItem,
    KpiConfigurationValidationResult,
)
from ada.configuration.kpi_configuration.models import KpiConfiguration
from ada.configuration.kpi_configuration.projection import KpiConfigurationProjection
from ada.configuration.kpi_configuration.source import (
    KpiConfigurationSourceDocument,
    build_kpi_configuration_digest,
)


@dataclass(frozen=True, slots=True)
class KpiConfigurationServices:
    administration: KpiConfigurationAdministrationService
    projection_workflow: KpiConfigurationProjectionWorkflow


class KpiConfigurationAdministrationService:
    def __init__(
        self,
        *,
        source: KpiConfigurationSource,
        publisher: KpiConfigurationPublisher,
        destinations: KpiDestinationCatalogProvider,
        audit_actor_provider: KpiConfigurationAuditActorProvider,
    ) -> None:
        self._source = source
        self._publisher = publisher
        self._destinations = destinations
        self._audit_actor_provider = audit_actor_provider

    def load_source(self) -> KpiConfigurationSourceDocument | None:
        return self._source.load()

    def load_configuration(self) -> KpiConfiguration | None:
        document = self.load_source()
        return document.configuration if document is not None else None

    def list_history(
        self,
        *,
        limit: int = 20,
    ) -> tuple[KpiConfigurationSourceDocument, ...]:
        return self._source.list_history(limit=limit)

    def load_revision_configuration(self, revision: str) -> KpiConfiguration:
        normalized = revision.strip() if isinstance(revision, str) else ''
        document = self._source.load_revision(normalized) if normalized else None
        if document is None:
            raise KpiConfigurationSourceError('KPI configuration revision does not exist')
        return document.configuration

    def validate_configuration(
        self,
        configuration: KpiConfiguration,
    ) -> KpiConfigurationValidationResult:
        validated = _require_configuration(configuration)
        catalog = self._destinations.load()
        issues = _validate_configuration(validated, catalog)
        return KpiConfigurationValidationResult(
            draft_revision=build_kpi_configuration_digest(validated),
            valid=not any(issue.level == 'error' for issue in issues),
            audit=_audit_record(self._audit_actor_provider),
            tool_projection_revision=(
                catalog.tool_projection_revision if catalog is not None else None
            ),
            issues=issues,
            summary=_configuration_summary(validated),
        )

    def publish_configuration(
        self,
        configuration: KpiConfiguration,
        *,
        expected_source_revision: str | None,
    ) -> KpiConfigurationPublicationResult:
        validated = _require_configuration(configuration)
        current = self._source.load()
        current_revision = current.revision if current is not None else None
        if current_revision != expected_source_revision:
            raise KpiConfigurationSourceError('KPI source revision changed before publication')
        catalog = self._require_catalog()
        issues = _validate_configuration(validated, catalog)
        if any(issue.level == 'error' for issue in issues):
            raise KpiConfigurationValidationError(
                'KPI configuration must be valid before publication'
            )
        audit = _audit_record(self._audit_actor_provider)
        document = KpiConfigurationSourceDocument.create(
            configuration=validated,
            saved_by=audit.actor,
            saved_at_utc=audit.occurred_at_utc,
        )
        summary = _configuration_summary(validated)
        if current_revision == document.revision:
            return KpiConfigurationPublicationResult(
                source_revision=document.revision,
                published=False,
                audit=audit,
                tool_projection_revision=catalog.tool_projection_revision,
                summary=summary,
            )
        self._require_catalog(expected_revision=catalog.tool_projection_revision)
        self._publisher.publish(document, expected_revision=expected_source_revision)
        return KpiConfigurationPublicationResult(
            source_revision=document.revision,
            published=True,
            audit=audit,
            tool_projection_revision=catalog.tool_projection_revision,
            summary=summary,
        )

    def _require_catalog(
        self,
        *,
        expected_revision: str | None = None,
    ) -> KpiDestinationCatalog:
        catalog = self._destinations.load()
        if catalog is None:
            raise KpiConfigurationValidationError('Tool projection is not available')
        if expected_revision is not None and catalog.tool_projection_revision != expected_revision:
            raise KpiConfigurationValidationError(
                'Tool projection revision changed before publication'
            )
        return catalog


class KpiConfigurationProjectionWorkflow:
    def __init__(
        self,
        *,
        source: KpiConfigurationSource,
        projection: KpiConfigurationProjectionRepository,
        destinations: KpiDestinationCatalogProvider,
        audit_actor_provider: KpiConfigurationAuditActorProvider,
    ) -> None:
        self._source = source
        self._projection = projection
        self._destinations = destinations
        self._audit_actor_provider = audit_actor_provider

    def get_status(self) -> KpiConfigurationStatus:
        source = self._source.load()
        active = self._projection.load()
        return KpiConfigurationStatus(
            source_revision=source.revision if source is not None else None,
            source_audit=(
                KpiConfigurationAuditRecord(
                    actor=source.saved_by,
                    occurred_at_utc=source.saved_at_utc,
                )
                if source is not None
                else None
            ),
            active_revision=active.revision if active is not None else None,
            active_source_revision=(active.source_revision if active is not None else None),
            active_tool_projection_revision=(
                active.tool_projection_revision if active is not None else None
            ),
            projection_audit=(
                KpiConfigurationAuditRecord(
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
    ) -> KpiConfigurationProjectionResult:
        expected = (
            expected_source_revision.strip() if isinstance(expected_source_revision, str) else ''
        )
        if not expected:
            raise KpiConfigurationProjectionError('Expected KPI source revision must not be empty')
        source = self._require_source(expected)
        catalog = self._require_catalog()
        issues = _validate_configuration(source.configuration, catalog)
        if any(issue.level == 'error' for issue in issues):
            raise KpiConfigurationProjectionError(
                'Published KPI configuration is not valid for projection'
            )
        active = self._projection.load()
        if (
            active is not None
            and active.source_revision == expected
            and active.tool_projection_revision == catalog.tool_projection_revision
        ):
            self._require_source(expected)
            self._require_catalog(expected_revision=catalog.tool_projection_revision)
            return KpiConfigurationProjectionResult(
                source_revision=source.revision,
                projection_revision=active.revision,
                tool_projection_revision=active.tool_projection_revision,
                projected=False,
                audit=KpiConfigurationAuditRecord(
                    actor=active.projected_by,
                    occurred_at_utc=active.projected_at_utc,
                ),
                issues=issues,
                summary=_configuration_summary(source.configuration),
            )
        audit = _audit_record(self._audit_actor_provider)
        candidate = KpiConfigurationProjection.create(
            configuration=source.configuration,
            source_revision=source.revision,
            tool_projection_revision=catalog.tool_projection_revision,
            projected_by=audit.actor,
            projected_at_utc=audit.occurred_at_utc,
        )
        self._require_source(expected)
        self._require_catalog(expected_revision=catalog.tool_projection_revision)
        saved = self._projection.save(candidate)
        self._require_source(expected)
        self._require_catalog(expected_revision=catalog.tool_projection_revision)
        return KpiConfigurationProjectionResult(
            source_revision=source.revision,
            projection_revision=saved.revision,
            tool_projection_revision=saved.tool_projection_revision,
            projected=True,
            audit=KpiConfigurationAuditRecord(
                actor=saved.projected_by,
                occurred_at_utc=saved.projected_at_utc,
            ),
            issues=issues,
            summary=_configuration_summary(source.configuration),
        )

    def _require_source(
        self,
        expected_revision: str,
    ) -> KpiConfigurationSourceDocument:
        document = self._source.load()
        if document is None:
            raise KpiConfigurationSourceError('KPI configuration source does not exist')
        if document.revision != expected_revision:
            raise KpiConfigurationProjectionError('KPI source revision changed before projection')
        return document

    def _require_catalog(
        self,
        *,
        expected_revision: str | None = None,
    ) -> KpiDestinationCatalog:
        catalog = self._destinations.load()
        if catalog is None:
            raise KpiConfigurationProjectionError('Tool projection is not available')
        if expected_revision is not None and catalog.tool_projection_revision != expected_revision:
            raise KpiConfigurationProjectionError(
                'Tool projection revision changed before KPI projection'
            )
        return catalog


def compose_kpi_configuration_services(
    *,
    source: KpiConfigurationSource,
    publisher: KpiConfigurationPublisher,
    projection: KpiConfigurationProjectionRepository,
    destinations: KpiDestinationCatalogProvider,
    audit_actor_provider: KpiConfigurationAuditActorProvider,
) -> KpiConfigurationServices:
    return KpiConfigurationServices(
        administration=KpiConfigurationAdministrationService(
            source=source,
            publisher=publisher,
            destinations=destinations,
            audit_actor_provider=audit_actor_provider,
        ),
        projection_workflow=KpiConfigurationProjectionWorkflow(
            source=source,
            projection=projection,
            destinations=destinations,
            audit_actor_provider=audit_actor_provider,
        ),
    )


def _require_configuration(configuration: KpiConfiguration) -> KpiConfiguration:
    if not isinstance(configuration, KpiConfiguration):
        raise KpiConfigurationValidationError('KPI configuration is invalid')
    return configuration


def _validate_configuration(
    configuration: KpiConfiguration,
    catalog: KpiDestinationCatalog | None,
) -> tuple[KpiConfigurationIssue, ...]:
    _require_configuration(configuration)
    if catalog is None:
        return (
            KpiConfigurationIssue(
                code='kpi.tool_projection.missing',
                message='Tool projection is not available',
                path='bindings',
            ),
        )
    available = catalog.keys
    issues: list[KpiConfigurationIssue] = []
    for binding_index, binding in enumerate(configuration.bindings):
        for destination_index, destination_key in enumerate(binding.destination_keys):
            if destination_key not in available:
                issues.append(
                    KpiConfigurationIssue(
                        code='kpi.destination.unavailable',
                        message=f'KPI destination {destination_key!r} is not available',
                        path=(f'bindings[{binding_index}].destination_keys[{destination_index}]'),
                    )
                )
    return tuple(issues)


def _configuration_summary(
    configuration: KpiConfiguration,
) -> tuple[KpiConfigurationSummaryItem, ...]:
    destinations = {
        destination
        for binding in configuration.bindings
        for destination in binding.destination_keys
    }
    return (
        KpiConfigurationSummaryItem('KPIs', str(len(configuration.bindings))),
        KpiConfigurationSummaryItem(
            'Delivery',
            str(sum(binding.delivery_enabled for binding in configuration.bindings)),
        ),
        KpiConfigurationSummaryItem(
            'Latest',
            str(sum(binding.latest_enabled for binding in configuration.bindings)),
        ),
        KpiConfigurationSummaryItem(
            'Series',
            str(sum(binding.series_enabled for binding in configuration.bindings)),
        ),
        KpiConfigurationSummaryItem('Destinos', str(len(destinations))),
    )


def _audit_record(
    provider: KpiConfigurationAuditActorProvider,
) -> KpiConfigurationAuditRecord:
    return KpiConfigurationAuditRecord(
        actor=provider(),
        occurred_at_utc=datetime.now(UTC),
    )
