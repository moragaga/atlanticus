from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Generic, TypeVar

from atlanticus.web.source.models import SourceKey, SourceReleaseId, SourceReleaseRef

PayloadT = TypeVar('PayloadT')


class ProjectionAlignment(str, Enum):
    NEVER_PROJECTED = 'NEVER_PROJECTED'
    CURRENT = 'CURRENT'
    OUTDATED = 'OUTDATED'


class ProjectionAttemptOutcome(str, Enum):
    SUCCESS = 'SUCCESS'
    FAILED = 'FAILED'


@dataclass(frozen=True, slots=True)
class ProjectionTarget:
    source_key: SourceKey
    source_release: SourceReleaseRef

    @property
    def source_release_id(self) -> SourceReleaseId:
        return self.source_release.release_id


@dataclass(frozen=True, slots=True)
class ProjectionRecord(Generic[PayloadT]):
    source_key: SourceKey
    source_release_id: SourceReleaseId
    source_published_at_utc: datetime
    projected_at_utc: datetime
    payload: PayloadT

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            'source_published_at_utc',
            _normalize_utc(self.source_published_at_utc, 'Source publication time'),
        )
        object.__setattr__(
            self,
            'projected_at_utc',
            _normalize_utc(self.projected_at_utc, 'Projection time'),
        )

    @property
    def source_release(self) -> SourceReleaseRef:
        return SourceReleaseRef(
            release_id=self.source_release_id,
            published_at_utc=self.source_published_at_utc,
        )


@dataclass(frozen=True, slots=True)
class ProjectionStatus:
    alignment: ProjectionAlignment
    source_current_release: SourceReleaseRef | None
    projected_source_release: SourceReleaseRef | None


@dataclass(frozen=True, slots=True)
class ProjectionExecutionResult(Generic[PayloadT]):
    target: ProjectionTarget
    projection: ProjectionRecord[PayloadT]
    outcome: ProjectionAttemptOutcome = field(
        default=ProjectionAttemptOutcome.SUCCESS,
        init=False,
    )

    def __post_init__(self) -> None:
        if self.projection.source_key != self.target.source_key:
            raise ValueError('Projection result source key does not match target')
        if self.projection.source_release != self.target.source_release:
            raise ValueError('Projection result source release does not match target')


def _normalize_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f'{label} must be timezone-aware')
    return value.astimezone(timezone.utc)
