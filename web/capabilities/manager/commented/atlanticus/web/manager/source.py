# Espejo pedagógico del archivo productivo equivalente.
# Define la frontera que Manager necesita de servicios Source. Los resultados transportan SourceSnapshot, releases y PublishResult genéricos.
# Los comentarios no alteran la estructura ejecutable ni el comportamiento del archivo productivo.

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from atlanticus.web.manager.errors import ManagerProjectionError
from atlanticus.web.manager.projection import ProjectionAuditRecord, ProjectionSummaryItem
from atlanticus.web.source.models import HistoryPage, PublishResult, SourceReleaseRef, SourceSnapshot


@dataclass(frozen=True, slots=True)
class SourceReadResult:
    snapshot: SourceSnapshot
    payload: dict[str, object] | None

    def __post_init__(self) -> None:
        if (self.snapshot.current is not None) != (self.payload is not None):
            raise ManagerProjectionError(
                'Source read result must include payload exactly when source exists'
            )
        if self.payload is not None:
            object.__setattr__(self, 'payload', deepcopy(self.payload))


@dataclass(frozen=True, slots=True)
class SourceHistoryReadResult:
    release_ref: SourceReleaseRef
    payload: dict[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, 'payload', deepcopy(self.payload))


@dataclass(frozen=True, slots=True)
class SourcePublicationResult:
    source: PublishResult
    audit: ProjectionAuditRecord
    summary: tuple[ProjectionSummaryItem, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, 'summary', tuple(self.summary))


@runtime_checkable
class SourceReaderWorkflow(Protocol):
    def load_current_source(self) -> SourceReadResult: ...


@runtime_checkable
class SourceHistoryWorkflow(Protocol):
    def list_history(self, *, limit: int = 20) -> HistoryPage: ...

    def load_history_release(
        self,
        release_ref: SourceReleaseRef,
    ) -> SourceHistoryReadResult: ...


@runtime_checkable
class SourcePublicationWorkflow(Protocol):
    def get_source_snapshot(self) -> SourceSnapshot: ...

    def publish_draft(
        self,
        payload: dict[str, object],
        expected_source_snapshot: SourceSnapshot,
    ) -> SourcePublicationResult: ...
