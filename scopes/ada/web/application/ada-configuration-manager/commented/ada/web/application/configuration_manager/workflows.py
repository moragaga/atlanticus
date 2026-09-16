# Espejo pedagógico: compone Source y validación de cada dominio con los protocolos genéricos del Manager.
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from ada.web.kpis.configuration import (
    KpiConfiguration,
    KpiConfigurationSourceError,
    KpiConfigurationValidationError,
    KpiDestinationCatalogProvider,
    KpiSourceService,
    validate_kpi_configuration_destinations,
)
from ada.web.kpis.definition import (
    KpiDefinitionConfiguration,
    KpiDefinitionSourceError,
    KpiDefinitionSourceService,
    KpiDefinitionValidationError,
    validate_kpi_definition_configuration,
)
from ada.web.tools.configuration import (
    ToolConfiguration,
    ToolConfigurationSourceError,
    ToolSourceService,
    validate_ada_operational_tool_configuration,
)
from ada.web.tools.errors import ToolConfigurationValidationError
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
from atlanticus.web.navigation.configuration import (
    NavigationConfigurationCatalog,
    NavigationSourceService,
)
from atlanticus.web.navigation.configuration.errors import (
    NavigationConfigurationSourceError,
    NavigationConfigurationValidationError,
)
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import HistoryPage, PublishResult, SourceKey, SourceReleaseRef, SourceSnapshot


# Cada SourceWorkflow adapta únicamente el modelo de dominio al protocolo genérico del Manager.
class NavigationManagerSourceWorkflow:
    def __init__(
        self,
        *,
        source: NavigationSourceService,
        audit_actor_provider: Callable[[], str],
    ) -> None:
        self._source = source
        self._audit_actor_provider = audit_actor_provider

    def get_source_snapshot(self) -> SourceSnapshot:
        return self._source.get_current()

    def load_current_source(self) -> SourceReadResult:
        snapshot = self._source.get_current()
        if snapshot.current is None:
            return SourceReadResult(snapshot=snapshot, payload=None)
        release = self._source.load_release(snapshot.current.release_ref)
        if self._source.get_current() != snapshot:
            raise NavigationConfigurationSourceError(
                'Navigation source changed while it was being loaded'
            )
        return SourceReadResult(snapshot=snapshot, payload=release.catalog.to_document())

    def list_history(self, *, limit: int = 20) -> HistoryPage:
        return self._source.query_history(page_size=limit)

    def load_history_release(
        self,
        release_ref: SourceReleaseRef,
    ) -> SourceHistoryReadResult:
        release = self._source.load_release(release_ref)
        return SourceHistoryReadResult(
            release_ref=release_ref,
            payload=release.catalog.to_document(),
        )

    def publish_draft(
        self,
        payload: dict[str, object],
        expected_source_snapshot: SourceSnapshot,
    ) -> SourcePublicationResult:
        _require_source_key(expected_source_snapshot, self._source.source_key)
        catalog = NavigationConfigurationCatalog.from_document(dict(payload))
        actor = _audit_actor(self._audit_actor_provider)
        published = self._source.publish_catalog(
            catalog,
            published_by=actor,
            expected_concurrency_token=expected_source_snapshot.concurrency_token,
            basis_release=_basis_release(expected_source_snapshot),
        )
        return _publication_result(published, actor)


class NavigationManagerDraftValidationWorkflow:
    def __init__(self, *, audit_actor_provider: Callable[[], str]) -> None:
        self._audit_actor_provider = audit_actor_provider

    def validate_draft(self, payload: dict[str, object]) -> DraftValidationResult:
        revision = build_workspace_revision(payload)
        audit = _audit(self._audit_actor_provider)
        try:
            catalog = NavigationConfigurationCatalog.from_document(dict(payload))
        except NavigationConfigurationValidationError as error:
            return _invalid(
                revision,
                audit,
                code='navigation.configuration.invalid',
                message=str(error),
            )
        return DraftValidationResult(
            draft_revision=revision,
            valid=True,
            audit=audit,
            summary=(
                ProjectionSummaryItem('Enlaces raíz', str(len(catalog.links))),
                ProjectionSummaryItem('Grupos', str(len(catalog.groups))),
                ProjectionSummaryItem(
                    'Enlaces en grupos',
                    str(sum(len(group.links) for group in catalog.groups)),
                ),
            ),
        )


class ToolManagerSourceWorkflow:
    def __init__(
        self,
        *,
        source: ToolSourceService,
        audit_actor_provider: Callable[[], str],
    ) -> None:
        self._source = source
        self._audit_actor_provider = audit_actor_provider

    def get_source_snapshot(self) -> SourceSnapshot:
        return self._source.get_current()

    def load_current_source(self) -> SourceReadResult:
        snapshot = self._source.get_current()
        if snapshot.current is None:
            return SourceReadResult(snapshot=snapshot, payload=None)
        release = self._source.load_release(snapshot.current.release_ref)
        if self._source.get_current() != snapshot:
            raise ToolConfigurationSourceError('Tool source changed while it was being loaded')
        return SourceReadResult(
            snapshot=snapshot,
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
            release_ref=release_ref,
            payload=release.configuration.to_document(),
        )

    def publish_draft(
        self,
        payload: dict[str, object],
        expected_source_snapshot: SourceSnapshot,
    ) -> SourcePublicationResult:
        _require_source_key(expected_source_snapshot, self._source.source_key)
        configuration = ToolConfiguration.from_document(dict(payload))
        actor = _audit_actor(self._audit_actor_provider)
        published = self._source.publish_configuration(
            configuration,
            published_by=actor,
            expected_concurrency_token=expected_source_snapshot.concurrency_token,
            basis_release=_basis_release(expected_source_snapshot),
        )
        return _publication_result(published, actor)


# La validación trabaja sobre el contrato final y no persiste ni reconstruye identidad de Source.
class ToolManagerDraftValidationWorkflow:
    def __init__(self, *, audit_actor_provider: Callable[[], str]) -> None:
        self._audit_actor_provider = audit_actor_provider

    def validate_draft(self, payload: dict[str, object]) -> DraftValidationResult:
        revision = build_workspace_revision(payload)
        audit = _audit(self._audit_actor_provider)
        try:
            configuration = ToolConfiguration.from_document(dict(payload))
            validate_ada_operational_tool_configuration(configuration)
        except ToolConfigurationValidationError as error:
            return _invalid(
                revision,
                audit,
                code='tools.configuration.invalid',
                message=str(error),
            )
        structure = configuration.structure
        return DraftValidationResult(
            draft_revision=revision,
            valid=True,
            audit=audit,
            summary=(
                ProjectionSummaryItem('Herramienta', configuration.display_name),
                ProjectionSummaryItem(
                    'Fuentes',
                    str(len(configuration.source_consumption.source_keys)),
                ),
                ProjectionSummaryItem(
                    'Componentes',
                    str(len(structure.components) if structure is not None else 0),
                ),
            ),
        )


class KpiConfigurationManagerSourceWorkflow:
    def __init__(
        self,
        *,
        source: KpiSourceService,
        audit_actor_provider: Callable[[], str],
    ) -> None:
        self._source = source
        self._audit_actor_provider = audit_actor_provider

    def get_source_snapshot(self) -> SourceSnapshot:
        return self._source.get_current()

    def load_current_source(self) -> SourceReadResult:
        snapshot = self._source.get_current()
        if snapshot.current is None:
            return SourceReadResult(snapshot=snapshot, payload=None)
        release = self._source.load_release(snapshot.current.release_ref)
        if self._source.get_current() != snapshot:
            raise KpiConfigurationSourceError('KPI source changed while it was being loaded')
        return SourceReadResult(
            snapshot=snapshot,
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
            release_ref=release_ref,
            payload=release.configuration.to_document(),
        )

    def publish_draft(
        self,
        payload: dict[str, object],
        expected_source_snapshot: SourceSnapshot,
    ) -> SourcePublicationResult:
        _require_source_key(expected_source_snapshot, self._source.source_key)
        configuration = KpiConfiguration.from_document(dict(payload))
        actor = _audit_actor(self._audit_actor_provider)
        published = self._source.publish_configuration(
            configuration,
            published_by=actor,
            expected_concurrency_token=expected_source_snapshot.concurrency_token,
            basis_release=_basis_release(expected_source_snapshot),
        )
        return _publication_result(published, actor)


# KPI valida contra el catálogo derivado de la proyección exacta de Tools.
class KpiConfigurationManagerDraftValidationWorkflow:
    def __init__(
        self,
        *,
        destinations: KpiDestinationCatalogProvider,
        audit_actor_provider: Callable[[], str],
    ) -> None:
        self._destinations = destinations
        self._audit_actor_provider = audit_actor_provider

    def validate_draft(self, payload: dict[str, object]) -> DraftValidationResult:
        revision = build_workspace_revision(payload)
        audit = _audit(self._audit_actor_provider)
        try:
            configuration = KpiConfiguration.from_document(dict(payload))
            destinations = self._destinations.load()
            if destinations is None:
                return _invalid(
                    revision,
                    audit,
                    code='kpis.tools-projection.unavailable',
                    message='Tool projection is not available',
                )
            validate_kpi_configuration_destinations(
                configuration,
                destinations.catalog,
            )
        except KpiConfigurationValidationError as error:
            return _invalid(
                revision,
                audit,
                code='kpis.configuration.invalid',
                message=str(error),
            )
        destination_keys = {
            destination
            for binding in configuration.bindings
            for destination in binding.destination_keys
        }
        return DraftValidationResult(
            draft_revision=revision,
            valid=True,
            audit=audit,
            summary=(
                ProjectionSummaryItem('KPI', str(len(configuration.bindings))),
                ProjectionSummaryItem('Destinos', str(len(destination_keys))),
            ),
        )


class KpiDefinitionManagerSourceWorkflow:
    def __init__(
        self,
        *,
        source: KpiDefinitionSourceService,
        audit_actor_provider: Callable[[], str],
    ) -> None:
        self._source = source
        self._audit_actor_provider = audit_actor_provider

    def get_source_snapshot(self) -> SourceSnapshot:
        return self._source.get_current()

    def load_current_source(self) -> SourceReadResult:
        snapshot = self._source.get_current()
        if snapshot.current is None:
            return SourceReadResult(snapshot=snapshot, payload=None)
        release = self._source.load_release(snapshot.current.release_ref)
        if self._source.get_current() != snapshot:
            raise KpiDefinitionSourceError(
                'KPI Definition source changed while it was being loaded'
            )
        return SourceReadResult(
            snapshot=snapshot,
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
            release_ref=release_ref,
            payload=release.configuration.to_document(),
        )

    def publish_draft(
        self,
        payload: dict[str, object],
        expected_source_snapshot: SourceSnapshot,
    ) -> SourcePublicationResult:
        _require_source_key(expected_source_snapshot, self._source.source_key)
        configuration = KpiDefinitionConfiguration.from_document(dict(payload))
        actor = _audit_actor(self._audit_actor_provider)
        published = self._source.publish_configuration(
            configuration,
            published_by=actor,
            expected_concurrency_token=expected_source_snapshot.concurrency_token,
            basis_release=_basis_release(expected_source_snapshot),
        )
        return _publication_result(published, actor)


# KPI Definition valida contra la proyección activa de KPI Configuration, sin authority paralela.
class KpiDefinitionManagerDraftValidationWorkflow:
    def __init__(
        self,
        *,
        kpi_configuration_projection: ProjectionStore[KpiConfiguration],
        kpi_configuration_source_key: SourceKey,
        audit_actor_provider: Callable[[], str],
    ) -> None:
        self._kpi_configuration_projection = kpi_configuration_projection
        self._kpi_configuration_source_key = kpi_configuration_source_key
        self._audit_actor_provider = audit_actor_provider

    def validate_draft(self, payload: dict[str, object]) -> DraftValidationResult:
        revision = build_workspace_revision(payload)
        audit = _audit(self._audit_actor_provider)
        try:
            configuration = KpiDefinitionConfiguration.from_document(dict(payload))
            kpi_projection = self._kpi_configuration_projection.get_active(
                self._kpi_configuration_source_key
            )
            if kpi_projection is None:
                return _invalid(
                    revision,
                    audit,
                    code='kpi-definitions.kpi-projection.unavailable',
                    message='KPI Configuration projection is not available',
                )
            if not isinstance(kpi_projection.payload, KpiConfiguration):
                return _invalid(
                    revision,
                    audit,
                    code='kpi-definitions.kpi-projection.invalid',
                    message='KPI Configuration projection payload is invalid',
                )
            validate_kpi_definition_configuration(
                configuration,
                kpi_projection.payload,
            )
        except KpiDefinitionValidationError as error:
            return _invalid(
                revision,
                audit,
                code='kpi-definitions.configuration.invalid',
                message=str(error),
            )
        return DraftValidationResult(
            draft_revision=revision,
            valid=True,
            audit=audit,
            summary=(
                ProjectionSummaryItem(
                    'Definiciones',
                    str(len(configuration.definitions)),
                ),
                ProjectionSummaryItem(
                    'Campos',
                    str(sum(len(definition.fields) for definition in configuration.definitions)),
                ),
            ),
        )


def _audit_actor(provider: Callable[[], str]) -> str:
    actor = provider().strip()
    if not actor:
        raise ValueError('Manager audit actor must not be empty')
    return actor


def _audit(provider: Callable[[], str]) -> ProjectionAuditRecord:
    return ProjectionAuditRecord(
        actor=_audit_actor(provider),
        occurred_at=datetime.now(UTC),
    )


def _invalid(
    revision: str,
    audit: ProjectionAuditRecord,
    *,
    code: str,
    message: str,
) -> DraftValidationResult:
    return DraftValidationResult(
        draft_revision=revision,
        valid=False,
        audit=audit,
        issues=(ProjectionIssue(code=code, message=message),),
    )


def _require_source_key(snapshot: SourceSnapshot, source_key: SourceKey) -> None:
    if snapshot.source_key != source_key:
        raise ValueError('Manager source snapshot uses a different source key')


def _basis_release(snapshot: SourceSnapshot) -> SourceReleaseRef | None:
    return snapshot.current.release_ref if snapshot.current is not None else None


def _publication_result(
    published: PublishResult,
    actor: str,
) -> SourcePublicationResult:
    return SourcePublicationResult(
        source=published,
        audit=ProjectionAuditRecord(
            actor=actor,
            occurred_at=published.release.release_ref.published_at_utc,
        ),
    )
