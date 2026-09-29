from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from ada.web.operational.identification import (
    CATALOG_SOURCE_KEY,
    OperationalCatalog,
    OperationalIdentificationError,
    OperationalIdentificationService,
    OperationalReferenceError,
    Position,
)
from ada.web.operational.identification.models import OperationalDocument
from ada.web.operational.identification.projection import create_operational_projection_service
from ada.web.operational.identification.source import OperationalSourceService
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
from atlanticus.web.projection.service import SourceProjectionService
from atlanticus.web.projection.store import ProjectionStore
from atlanticus.web.source.models import HistoryPage, SourceReleaseRef, SourceSnapshot
from atlanticus.web.source.store import SourceStore

OPERATIONAL_CATALOG_SOURCE_SERVICE = 'ada.configuration-manager.operational-catalog.source'
OPERATIONAL_CATALOG_SOURCE_READER_SERVICE = (
    'ada.configuration-manager.operational-catalog.source-reader'
)
OPERATIONAL_CATALOG_SOURCE_HISTORY_SERVICE = (
    'ada.configuration-manager.operational-catalog.source-history'
)
OPERATIONAL_CATALOG_PROJECTION_SERVICE = 'ada.configuration-manager.operational-catalog.projection'
OPERATIONAL_CATALOG_DRAFT_VALIDATION_SERVICE = (
    'ada.configuration-manager.operational-catalog.validation'
)


class OperationalCatalogDraftEditor:
    def add_position(
        self,
        payload: dict[str, object],
        *,
        label: str,
        active: bool = True,
    ) -> tuple[dict[str, object], str]:
        catalog = OperationalCatalog.from_document(payload)
        existing = {position.id for position in catalog.positions}
        for _attempt in range(10):
            position_id = f'position_{uuid4().hex}'
            if position_id not in existing:
                break
        else:
            raise OperationalReferenceError('Could not generate a unique position identifier')
        updated = OperationalCatalog(
            positions=(*catalog.positions, Position(id=position_id, label=label, active=active))
        )
        return updated.to_document(), position_id

    def update_position(
        self,
        payload: dict[str, object],
        *,
        position_id: str,
        label: str,
        active: bool,
    ) -> dict[str, object]:
        catalog = OperationalCatalog.from_document(payload)
        previous = catalog.position(position_id)
        if previous is None:
            raise OperationalReferenceError('Position is not in the operational draft')
        replacement = Position(id=previous.id, label=label, active=active)
        return OperationalCatalog(
            positions=tuple(
                replacement if position.id == previous.id else position
                for position in catalog.positions
            )
        ).to_document()


class OperationalCatalogManagerSourceWorkflow:
    def __init__(
        self,
        *,
        service: OperationalIdentificationService,
        source_store: SourceStore,
        audit_actor_provider: Callable[[], str],
    ) -> None:
        self._service = service
        self._source = OperationalSourceService(store=source_store)
        self._audit_actor_provider = audit_actor_provider

    def get_source_snapshot(self) -> SourceSnapshot:
        return self._source.snapshot(CATALOG_SOURCE_KEY)

    def load_current_source(self) -> SourceReadResult:
        snapshot, value = self._source.current(CATALOG_SOURCE_KEY)
        if self._source.snapshot(CATALOG_SOURCE_KEY) != snapshot:
            raise OperationalReferenceError('Operational catalog source changed while being loaded')
        if value is None:
            return SourceReadResult(snapshot=snapshot, payload=None)
        if not isinstance(value, OperationalCatalog):
            raise OperationalReferenceError('Operational catalog source has an invalid type')
        return SourceReadResult(snapshot=snapshot, payload=value.to_document())

    def list_history(self, *, limit: int = 20) -> HistoryPage:
        return self._source.history(CATALOG_SOURCE_KEY, limit=limit)

    def load_history_release(self, release_ref: SourceReleaseRef) -> SourceHistoryReadResult:
        value = self._source.read(CATALOG_SOURCE_KEY, release_ref)
        if not isinstance(value, OperationalCatalog):
            raise OperationalReferenceError('Operational catalog history has an invalid type')
        return SourceHistoryReadResult(release_ref=release_ref, payload=value.to_document())

    def publish_draft(
        self,
        payload: dict[str, object],
        expected_source_snapshot: SourceSnapshot,
    ) -> SourcePublicationResult:
        if expected_source_snapshot.source_key != CATALOG_SOURCE_KEY:
            raise OperationalReferenceError('Operational draft belongs to a different source')
        current, _value = self._service.catalog_for_edit()
        if current != expected_source_snapshot:
            raise OperationalReferenceError('Operational catalog changed before publication')
        catalog = OperationalCatalog.from_document(payload)
        actor = self._audit_actor_provider().strip()
        if not actor:
            raise OperationalReferenceError('Operational catalog publication actor is required')
        published = self._service.publish_catalog(
            catalog,
            actor=actor,
            expected=expected_source_snapshot,
        )
        return SourcePublicationResult(
            source=published,
            audit=ProjectionAuditRecord(
                actor=actor,
                occurred_at=published.release.release_ref.published_at_utc,
            ),
            summary=_catalog_summary(catalog),
        )


class OperationalCatalogManagerDraftValidationWorkflow:
    def __init__(
        self,
        *,
        service: OperationalIdentificationService,
        audit_actor_provider: Callable[[], str],
    ) -> None:
        self._service = service
        self._audit_actor_provider = audit_actor_provider

    def validate_draft(self, payload: dict[str, object]) -> DraftValidationResult:
        revision = build_workspace_revision(payload)
        audit = ProjectionAuditRecord(
            actor=self._audit_actor_provider().strip(),
            occurred_at=datetime.now(UTC),
        )
        try:
            catalog = OperationalCatalog.from_document(payload)
            _snapshot, previous = self._service.catalog_for_edit()
            catalog.validate_revision(previous)
        except OperationalIdentificationError as error:
            return DraftValidationResult(
                draft_revision=revision,
                valid=False,
                audit=audit,
                issues=(
                    ProjectionIssue(
                        code='ada.operational.catalog.invalid',
                        message=str(error),
                    ),
                ),
            )
        return DraftValidationResult(
            draft_revision=revision,
            valid=True,
            audit=audit,
            summary=_catalog_summary(catalog),
        )


@dataclass(frozen=True, slots=True)
class OperationalCatalogManagerContracts:
    source: OperationalCatalogManagerSourceWorkflow
    validation: OperationalCatalogManagerDraftValidationWorkflow
    projection: SourceProjectionService[OperationalDocument]
    editor: OperationalCatalogDraftEditor


def compose_operational_catalog_manager_contracts(
    *,
    service: OperationalIdentificationService,
    source_store: SourceStore,
    projection_store: ProjectionStore[OperationalDocument],
    audit_actor_provider: Callable[[], str],
) -> OperationalCatalogManagerContracts:
    return OperationalCatalogManagerContracts(
        source=OperationalCatalogManagerSourceWorkflow(
            service=service,
            source_store=source_store,
            audit_actor_provider=audit_actor_provider,
        ),
        validation=OperationalCatalogManagerDraftValidationWorkflow(
            service=service,
            audit_actor_provider=audit_actor_provider,
        ),
        projection=create_operational_projection_service(
            source=source_store,
            projection=projection_store,
        ),
        editor=OperationalCatalogDraftEditor(),
    )


def _catalog_summary(catalog: OperationalCatalog) -> tuple[ProjectionSummaryItem, ...]:
    return (
        ProjectionSummaryItem('Cargos configurados', str(len(catalog.positions))),
        ProjectionSummaryItem(
            'Cargos activos', str(sum(position.active for position in catalog.positions))
        ),
    )
