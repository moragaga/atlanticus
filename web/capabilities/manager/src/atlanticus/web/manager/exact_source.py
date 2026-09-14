from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from atlanticus.web.manager.projection import ProjectionAuditRecord, ProjectionSummaryItem
from atlanticus.web.source.models import PublishResult, SourceSnapshot


@dataclass(frozen=True, slots=True)
class ExactSourcePublicationResult:
    source: PublishResult
    audit: ProjectionAuditRecord
    summary: tuple[ProjectionSummaryItem, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, 'summary', tuple(self.summary))


@runtime_checkable
class ExactSourcePublicationWorkflow(Protocol):
    def get_source_snapshot(self) -> SourceSnapshot: ...

    def publish_draft_exact(
        self,
        payload: dict[str, object],
        expected_source_snapshot: SourceSnapshot,
    ) -> ExactSourcePublicationResult: ...
