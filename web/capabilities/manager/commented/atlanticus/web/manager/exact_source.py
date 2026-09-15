# Contratos genéricos para leer y publicar Source con identidad exacta.
# El payload leído viaja junto al SourceSnapshot para que Manager pueda distinguir
# entre un workspace local limpio y contenido realmente publicado sin usar revisiones string.
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from atlanticus.web.manager.errors import ManagerProjectionError
from atlanticus.web.manager.projection import ProjectionAuditRecord, ProjectionSummaryItem
from atlanticus.web.source.models import PublishResult, SourceSnapshot


@dataclass(frozen=True, slots=True)
class ExactSourceReadResult:
    snapshot: SourceSnapshot
    payload: dict[str, object] | None

    def __post_init__(self) -> None:
        has_source = self.snapshot.current is not None
        has_payload = self.payload is not None
        if has_source != has_payload:
            raise ManagerProjectionError(
                'Exact source read result must include payload exactly when source exists'
            )
        if self.payload is not None:
            object.__setattr__(self, 'payload', deepcopy(self.payload))


@dataclass(frozen=True, slots=True)
class ExactSourcePublicationResult:
    source: PublishResult
    audit: ProjectionAuditRecord
    summary: tuple[ProjectionSummaryItem, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, 'summary', tuple(self.summary))


@runtime_checkable
class ExactSourceReaderWorkflow(Protocol):
    def load_current_source_exact(self) -> ExactSourceReadResult: ...


@runtime_checkable
class ExactSourcePublicationWorkflow(Protocol):
    def get_source_snapshot(self) -> SourceSnapshot: ...

    def publish_draft_exact(
        self,
        payload: dict[str, object],
        expected_source_snapshot: SourceSnapshot,
    ) -> ExactSourcePublicationResult: ...
