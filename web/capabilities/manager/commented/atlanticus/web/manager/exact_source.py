from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from atlanticus.web.manager.projection import ProjectionAuditRecord, ProjectionSummaryItem
from atlanticus.web.source.models import PublishResult, SourceSnapshot


@dataclass(frozen=True, slots=True)
class ExactSourcePublicationResult:
    # Conservamos el PublishResult tipado de Source. Así Manager recibe release metadata,
    # SourceReleaseRef y ConcurrencyToken sin degradarlos a una revisión textual legacy.
    source: PublishResult
    audit: ProjectionAuditRecord
    summary: tuple[ProjectionSummaryItem, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, 'summary', tuple(self.summary))


@runtime_checkable
class ExactSourcePublicationWorkflow(Protocol):
    # Este contrato es opt-in. No reemplaza todavía ConfigurationLifecycleWorkflow y permite
    # migrar módulos uno a uno sin convertir SourceReleaseId en un str legacy.
    def get_source_snapshot(self) -> SourceSnapshot: ...

    # El caller debe devolver exactamente el SourceSnapshot con el que abrió su borrador.
    # El workflow puede usar release_ref como basis_release y concurrency_token para el CAS.
    def publish_draft_exact(
        self,
        payload: dict[str, object],
        expected_source_snapshot: SourceSnapshot,
    ) -> ExactSourcePublicationResult: ...
