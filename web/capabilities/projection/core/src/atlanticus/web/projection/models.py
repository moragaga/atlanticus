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
    dependencies: tuple[ProjectionTarget, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            'dependencies',
            _normalize_dependencies(self.source_key, self.dependencies),
        )

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
    dependencies: tuple[ProjectionTarget, ...] = ()

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
        object.__setattr__(
            self,
            'dependencies',
            _normalize_dependencies(self.source_key, self.dependencies),
        )

    @property
    def source_release(self) -> SourceReleaseRef:
        return SourceReleaseRef(
            release_id=self.source_release_id,
            published_at_utc=self.source_published_at_utc,
        )

    @property
    def target(self) -> ProjectionTarget:
        return ProjectionTarget(
            source_key=self.source_key,
            source_release=self.source_release,
            dependencies=self.dependencies,
        )


@dataclass(frozen=True, slots=True)
class ProjectionStatus:
    alignment: ProjectionAlignment
    source_current_release: SourceReleaseRef | None
    projected_source_release: SourceReleaseRef | None
    current_dependencies: tuple[ProjectionTarget, ...] = ()
    projected_dependencies: tuple[ProjectionTarget, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            'current_dependencies',
            tuple(self.current_dependencies),
        )
        object.__setattr__(
            self,
            'projected_dependencies',
            tuple(self.projected_dependencies),
        )


@dataclass(frozen=True, slots=True)
class ProjectionExecutionResult(Generic[PayloadT]):
    target: ProjectionTarget
    projection: ProjectionRecord[PayloadT]
    outcome: ProjectionAttemptOutcome = field(
        default=ProjectionAttemptOutcome.SUCCESS,
        init=False,
    )

    def __post_init__(self) -> None:
        if self.projection.target != self.target:
            raise ValueError('Projection result target does not match requested target')


def _normalize_dependencies(
    source_key: SourceKey,
    dependencies: tuple[ProjectionTarget, ...],
) -> tuple[ProjectionTarget, ...]:
    normalized = tuple(dependencies)
    if not all(isinstance(dependency, ProjectionTarget) for dependency in normalized):
        raise TypeError('Projection dependencies must contain projection targets')
    keys = tuple(dependency.source_key for dependency in normalized)
    if source_key in keys:
        raise ValueError('Projection target must not depend on its own source key')
    if len(keys) != len(set(keys)):
        raise ValueError('Projection dependency source keys must be unique')
    return tuple(sorted(normalized, key=lambda dependency: dependency.source_key.value))


def _normalize_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f'{label} must be timezone-aware')
    return value.astimezone(timezone.utc)
