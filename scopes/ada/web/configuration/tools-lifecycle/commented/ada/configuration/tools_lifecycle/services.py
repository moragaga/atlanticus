from __future__ import annotations

# Servicios de administración y proyección por Tool con CAS y operaciones no-op.
from dataclasses import dataclass
from datetime import UTC, datetime

from ada.configuration.tools import (
    ToolConfiguration,
    ToolConfigurationValidationError,
    validate_ada_operational_tool_configuration,
)
from ada.configuration.tools_lifecycle.contracts import (
    ToolConfigurationAuditActorProvider,
    ToolConfigurationProjectionRepository,
    ToolConfigurationPublisher,
    ToolConfigurationSource,
)
from ada.configuration.tools_lifecycle.errors import (
    ToolLifecycleProjectionError,
    ToolLifecycleSourceError,
)
from ada.configuration.tools_lifecycle.lifecycle import (
    ToolLifecycleAuditRecord,
    ToolLifecycleIssue,
    ToolLifecycleProjectionResult,
    ToolLifecyclePublicationResult,
    ToolLifecycleStatus,
    ToolLifecycleSummaryItem,
    ToolLifecycleValidationResult,
)
from ada.configuration.tools_lifecycle.projection import ToolConfigurationProjectionSnapshot
from ada.configuration.tools_lifecycle.source import (
    ToolConfigurationSourceSnapshot,
    build_tool_configuration_digest,
)


@dataclass(frozen=True, slots=True)
class ToolLifecycleServices:
    administration: ToolAdministrationService
    projection_workflow: ToolProjectionWorkflow


class ToolAdministrationService:
    def __init__(
        self,
        *,
        source: ToolConfigurationSource,
        publisher: ToolConfigurationPublisher,
        audit_actor_provider: ToolConfigurationAuditActorProvider,
    ) -> None:
        self._source = source
        self._publisher = publisher
        self._audit_actor_provider = audit_actor_provider

    def load_source(self) -> ToolConfigurationSourceSnapshot | None:
        return self._source.load()

    def load_configuration(self) -> ToolConfiguration | None:
        document = self.load_source()
        return document.configuration if document is not None else None

    # Delega el orden y límite del historial a la implementación de Source.
    def list_history(
        self,
        *,
        limit: int = 20,
    ) -> tuple[ToolConfigurationSourceSnapshot, ...]:
        return self._source.list_history(limit=limit)

    # Recupera una revisión histórica como configuración editable de la Tool.
    def load_revision_configuration(
        self,
        revision: str,
    ) -> ToolConfiguration:
        normalized = revision.strip() if isinstance(revision, str) else ''
        document = self._source.load_revision(normalized) if normalized else None
        if document is None:
            raise ToolLifecycleSourceError('Tool revision does not exist')
        return document.configuration

    def validate_configuration(
        self,
        configuration: ToolConfiguration,
    ) -> ToolLifecycleValidationResult:
        validated = _require_configuration(configuration)
        audit = _audit_record(self._audit_actor_provider)
        issues = _validate_configuration(validated)
        return ToolLifecycleValidationResult(
            draft_revision=build_tool_configuration_digest(validated),
            valid=not any(issue.level == 'error' for issue in issues),
            audit=audit,
            issues=issues,
            summary=_configuration_summary(validated),
        )

    def publish_configuration(
        self,
        configuration: ToolConfiguration,
        *,
        expected_source_revision: str | None,
    ) -> ToolLifecyclePublicationResult:
        validated = _require_configuration(configuration)
        current = self._source.load()
        current_revision = current.revision if current is not None else None
        if current_revision != expected_source_revision:
            raise ToolLifecycleSourceError('Tool source revision changed before publication')
        issues = _validate_configuration(validated)
        if any(issue.level == 'error' for issue in issues):
            raise ToolConfigurationValidationError(
                'Tool Configuration must be valid before publication'
            )
        audit = _audit_record(self._audit_actor_provider)
        document = ToolConfigurationSourceSnapshot.create(
            configuration=validated,
            saved_by=audit.actor,
            saved_at_utc=audit.occurred_at_utc,
        )
        summary = _configuration_summary(validated)
        if current_revision == document.revision:
            return ToolLifecyclePublicationResult(
                source_revision=document.revision,
                published=False,
                audit=audit,
                summary=summary,
            )
        self._publisher.publish(
            document,
            expected_revision=expected_source_revision,
        )
        return ToolLifecyclePublicationResult(
            source_revision=document.revision,
            published=True,
            audit=audit,
            summary=summary,
        )


class ToolProjectionWorkflow:
    def __init__(
        self,
        *,
        source: ToolConfigurationSource,
        projection: ToolConfigurationProjectionRepository,
        audit_actor_provider: ToolConfigurationAuditActorProvider,
    ) -> None:
        self._source = source
        self._projection = projection
        self._audit_actor_provider = audit_actor_provider

    def get_status(self) -> ToolLifecycleStatus:
        source = self._source.load()
        active = self._projection.load()
        return ToolLifecycleStatus(
            source_revision=source.revision if source is not None else None,
            source_audit=(
                ToolLifecycleAuditRecord(
                    actor=source.saved_by,
                    occurred_at_utc=source.saved_at_utc,
                )
                if source is not None
                else None
            ),
            active_revision=active.revision if active is not None else None,
            active_source_revision=active.source_revision if active is not None else None,
            projection_audit=(
                ToolLifecycleAuditRecord(
                    actor=active.projected_by,
                    occurred_at_utc=active.projected_at_utc,
                )
                if active is not None
                else None
            ),
        )

    def project(self, expected_source_revision: str) -> ToolLifecycleProjectionResult:
        expected = (
            expected_source_revision.strip() if isinstance(expected_source_revision, str) else ''
        )
        if not expected:
            raise ToolLifecycleProjectionError('Expected Tool source revision must not be empty')
        source = self._require_source(expected)
        issues = _validate_configuration(source.configuration)
        if any(issue.level == 'error' for issue in issues):
            raise ToolLifecycleProjectionError(
                'Published Tool Configuration is not valid for projection'
            )
        active = self._projection.load()
        if active is not None and active.source_revision == expected:
            self._require_source(expected)
            return ToolLifecycleProjectionResult(
                source_revision=source.revision,
                projection_revision=active.revision,
                projected=False,
                audit=ToolLifecycleAuditRecord(
                    actor=active.projected_by,
                    occurred_at_utc=active.projected_at_utc,
                ),
                issues=issues,
                summary=_configuration_summary(source.configuration),
            )
        audit = _audit_record(self._audit_actor_provider)
        projection = ToolConfigurationProjectionSnapshot.create(
            configuration=source.configuration,
            source_revision=source.revision,
            projected_by=audit.actor,
            projected_at_utc=audit.occurred_at_utc,
        )
        self._require_source(expected)
        saved = self._projection.save(projection)
        self._require_source(expected)
        return ToolLifecycleProjectionResult(
            source_revision=source.revision,
            projection_revision=saved.revision,
            projected=True,
            audit=ToolLifecycleAuditRecord(
                actor=saved.projected_by,
                occurred_at_utc=saved.projected_at_utc,
            ),
            issues=issues,
            summary=_configuration_summary(source.configuration),
        )

    def _require_source(self, expected_revision: str) -> ToolConfigurationSourceSnapshot:
        document = self._source.load()
        if document is None:
            raise ToolLifecycleSourceError('Tool source does not exist')
        if document.revision != expected_revision:
            raise ToolLifecycleProjectionError('Tool source revision changed before projection')
        return document


def compose_tool_lifecycle_services(
    *,
    source: ToolConfigurationSource,
    publisher: ToolConfigurationPublisher,
    projection: ToolConfigurationProjectionRepository,
    audit_actor_provider: ToolConfigurationAuditActorProvider,
) -> ToolLifecycleServices:
    return ToolLifecycleServices(
        administration=ToolAdministrationService(
            source=source,
            publisher=publisher,
            audit_actor_provider=audit_actor_provider,
        ),
        projection_workflow=ToolProjectionWorkflow(
            source=source,
            projection=projection,
            audit_actor_provider=audit_actor_provider,
        ),
    )


def _require_configuration(configuration: ToolConfiguration) -> ToolConfiguration:
    if not isinstance(configuration, ToolConfiguration):
        raise ToolConfigurationValidationError('Tool Configuration is invalid')
    return configuration


def _validate_configuration(
    configuration: ToolConfiguration,
) -> tuple[ToolLifecycleIssue, ...]:
    try:
        validate_ada_operational_tool_configuration(configuration)
    except ToolConfigurationValidationError as error:
        return (
            ToolLifecycleIssue(
                code='tool.invalid',
                message=str(error),
                path='tool',
            ),
        )
    return ()


def _configuration_summary(
    configuration: ToolConfiguration,
) -> tuple[ToolLifecycleSummaryItem, ...]:
    structure = configuration.structure
    components = len(structure.components) if structure is not None else 0
    subcomponents = (
        sum(len(component.subcomponents) for component in structure.components)
        if structure is not None
        else 0
    )
    return (
        ToolLifecycleSummaryItem('Herramienta', configuration.display_name),
        ToolLifecycleSummaryItem('Fuentes', str(len(configuration.source_consumption.source_keys))),
        ToolLifecycleSummaryItem('Componentes', str(components)),
        ToolLifecycleSummaryItem('Subcomponentes', str(subcomponents)),
    )


def _audit_record(
    provider: ToolConfigurationAuditActorProvider,
) -> ToolLifecycleAuditRecord:
    return ToolLifecycleAuditRecord(
        actor=provider(),
        occurred_at_utc=datetime.now(UTC),
    )
