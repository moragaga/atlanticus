from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import PurePosixPath


@dataclass(frozen=True, slots=True)
class SourceKey:
    value: str

    def __post_init__(self) -> None:
        value = self.value.strip()
        if not value:
            raise ValueError('Source key must not be empty')
        if value in {'.', '..'} or '/' in value or '\\' in value or '\x00' in value:
            raise ValueError('Source key must be logical and must not contain path separators')
        object.__setattr__(self, 'value', value)


@dataclass(frozen=True, slots=True)
class SourceReleaseId:
    value: str

    def __post_init__(self) -> None:
        value = self.value.strip()
        if not value:
            raise ValueError('Source release id must not be empty')
        if '\x00' in value:
            raise ValueError('Source release id must not contain null characters')
        object.__setattr__(self, 'value', value)


@dataclass(frozen=True, slots=True)
class Digest:
    algorithm: str
    value: str

    def __post_init__(self) -> None:
        algorithm = self.algorithm.strip().lower()
        value = self.value.strip().lower()
        if not algorithm or not value:
            raise ValueError('Digest algorithm and value must not be empty')
        object.__setattr__(self, 'algorithm', algorithm)
        object.__setattr__(self, 'value', value)


@dataclass(frozen=True, slots=True)
class SourceReleaseRef:
    release_id: SourceReleaseId
    published_at_utc: datetime

    def __post_init__(self) -> None:
        published_at = _normalize_utc(self.published_at_utc, 'Source release publication time')
        object.__setattr__(self, 'published_at_utc', published_at)


@dataclass(frozen=True, slots=True)
class SourceResource:
    logical_path: str
    content: bytes

    def __post_init__(self) -> None:
        logical_path = _normalize_resource_path(self.logical_path)
        if not isinstance(self.content, bytes):
            raise TypeError('Source resource content must be bytes')
        object.__setattr__(self, 'logical_path', logical_path)


@dataclass(frozen=True, slots=True)
class SourceResourceMetadata:
    logical_path: str
    byte_length: int
    digest: Digest

    def __post_init__(self) -> None:
        logical_path = _normalize_resource_path(self.logical_path)
        if self.byte_length < 0:
            raise ValueError('Source resource byte length must not be negative')
        object.__setattr__(self, 'logical_path', logical_path)


@dataclass(frozen=True, slots=True)
class SourceReleaseSummary:
    release_ref: SourceReleaseRef
    content_hash: Digest


@dataclass(frozen=True, slots=True)
class SourceReleaseMetadata:
    schema_version: int
    source_key: SourceKey
    release_ref: SourceReleaseRef
    content_hash: Digest
    resources: tuple[SourceResourceMetadata, ...]
    previous_published_release: SourceReleaseRef | None = None
    basis_release: SourceReleaseRef | None = None

    def __post_init__(self) -> None:
        if self.schema_version < 1:
            raise ValueError('Source release schema version must be positive')
        _validate_unique_paths(item.logical_path for item in self.resources)


@dataclass(frozen=True, slots=True)
class SourceManifest:
    schema_version: int
    source_key: SourceKey
    current: SourceReleaseSummary

    def __post_init__(self) -> None:
        if self.schema_version < 1:
            raise ValueError('Source manifest schema version must be positive')


@dataclass(frozen=True, slots=True)
class ConcurrencyToken:
    value: str

    def __post_init__(self) -> None:
        value = self.value.strip()
        if not value:
            raise ValueError('Concurrency token must not be empty')
        object.__setattr__(self, 'value', value)


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    source_key: SourceKey
    current: SourceReleaseSummary | None
    concurrency_token: ConcurrencyToken | None

    def __post_init__(self) -> None:
        if self.current is None and self.concurrency_token is not None:
            raise ValueError('An empty source snapshot must not have a concurrency token')
        if self.current is not None and self.concurrency_token is None:
            raise ValueError('A published source snapshot must have a concurrency token')


@dataclass(frozen=True, slots=True)
class PublishRequest:
    source_key: SourceKey
    resources: tuple[SourceResource, ...]
    expected_concurrency_token: ConcurrencyToken | None
    basis_release: SourceReleaseRef | None = None

    def __post_init__(self) -> None:
        _validate_unique_paths(item.logical_path for item in self.resources)


@dataclass(frozen=True, slots=True)
class PublishResult:
    release: SourceReleaseMetadata
    snapshot: SourceSnapshot

    def __post_init__(self) -> None:
        if self.release.source_key != self.snapshot.source_key:
            raise ValueError('Published release and source snapshot must use the same source key')
        if self.snapshot.current is None:
            raise ValueError('Published result must contain a current source release')
        if self.release.release_ref != self.snapshot.current.release_ref:
            raise ValueError('Published release must match the current source snapshot')
        if self.release.content_hash != self.snapshot.current.content_hash:
            raise ValueError('Published release content hash must match the current source snapshot')


@dataclass(frozen=True, slots=True)
class HistoryQuery:
    source_key: SourceKey
    published_from_utc: datetime | None = None
    published_to_utc: datetime | None = None
    page_size: int = 20
    cursor: str | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.page_size <= 100:
            raise ValueError('History page size must be between 1 and 100')
        if self.published_from_utc is not None:
            object.__setattr__(
                self,
                'published_from_utc',
                _normalize_utc(self.published_from_utc, 'History lower bound'),
            )
        if self.published_to_utc is not None:
            object.__setattr__(
                self,
                'published_to_utc',
                _normalize_utc(self.published_to_utc, 'History upper bound'),
            )
        if (
            self.published_from_utc is not None
            and self.published_to_utc is not None
            and self.published_from_utc > self.published_to_utc
        ):
            raise ValueError('History lower bound must not be after upper bound')
        if self.cursor is not None and not self.cursor.strip():
            raise ValueError('History cursor must not be empty')


@dataclass(frozen=True, slots=True)
class HistoryPage:
    items: tuple[SourceReleaseSummary, ...]
    next_cursor: str | None = None


@dataclass(frozen=True, slots=True)
class IntegrityFailure:
    code: str
    message: str
    logical_path: str | None = None

    def __post_init__(self) -> None:
        code = self.code.strip()
        message = self.message.strip()
        if not code or not message:
            raise ValueError('Integrity failure code and message must not be empty')
        object.__setattr__(self, 'code', code)
        object.__setattr__(self, 'message', message)
        if self.logical_path is not None:
            object.__setattr__(self, 'logical_path', _normalize_resource_path(self.logical_path))


@dataclass(frozen=True, slots=True)
class IntegrityResult:
    release_ref: SourceReleaseRef
    checked_resources: int
    failures: tuple[IntegrityFailure, ...] = ()
    valid: bool = field(init=False)

    def __post_init__(self) -> None:
        if self.checked_resources < 0:
            raise ValueError('Checked resource count must not be negative')
        object.__setattr__(self, 'valid', not self.failures)


def _normalize_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f'{label} must be timezone-aware')
    normalized = value.astimezone(timezone.utc)
    return normalized


def _normalize_resource_path(value: str) -> str:
    candidate = value.strip().replace('\\', '/')
    path = PurePosixPath(candidate)
    if (
        not candidate
        or candidate.startswith('/')
        or path.is_absolute()
        or any(part in {'', '.', '..'} for part in path.parts)
        or '\x00' in candidate
    ):
        raise ValueError('Source resource path must be a safe relative logical path')
    return path.as_posix()


def _validate_unique_paths(paths: Iterable[str]) -> None:
    seen: set[str] = set()
    for path in paths:
        if not isinstance(path, str):
            raise TypeError('Source resource path must be a string')
        if path in seen:
            raise ValueError(f'Duplicate source resource path: {path}')
        seen.add(path)
