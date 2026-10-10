from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from ada.contracts.alarms.facts_stream import FactsStreamPosition, _load_cursor

_SEGMENT_PATH = re.compile(
    r'facts/year=\d{4}/month=\d{2}/day=\d{2}/hour=\d{2}/part-\d{4}\.jsonl'
)


class FactsSegmentInventoryError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SealedFactsSegment:
    relative_path: str
    size_bytes: int
    mtime_ns: int


@dataclass(frozen=True, slots=True)
class VerifiedSealedFactsSegment:
    relative_path: str
    size_bytes: int
    sha256: str


def list_sealed_facts_segments(*, root: Path) -> tuple[SealedFactsSegment, ...]:
    _validate_root(root)
    head = _load_cursor(root)
    active = head['segment_path']
    if active is None:
        return ()
    segments: list[SealedFactsSegment] = []
    for path in (root / 'facts').rglob('*.jsonl'):
        relative = path.relative_to(root).as_posix()
        if _SEGMENT_PATH.fullmatch(relative) is None:
            continue
        if relative >= active:
            continue
        _validate_file(root, path)
        stat = path.stat()
        segments.append(
            SealedFactsSegment(
                relative_path=relative,
                size_bytes=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
            )
        )
    if _load_cursor(root) != head:
        raise FactsSegmentInventoryError('FACTS publication cursor changed during inventory')
    return tuple(sorted(segments, key=lambda item: item.relative_path))


def verify_sealed_facts_segment(
    *, root: Path, segment: SealedFactsSegment
) -> VerifiedSealedFactsSegment:
    _validate_root(root)
    if not isinstance(segment, SealedFactsSegment):
        raise TypeError('segment must be a SealedFactsSegment')
    if _SEGMENT_PATH.fullmatch(segment.relative_path) is None:
        raise FactsSegmentInventoryError('Invalid FACTS segment path')
    head = _load_cursor(root)
    active = head['segment_path']
    if active is None or segment.relative_path >= active:
        raise FactsSegmentInventoryError('FACTS segment is not sealed')
    path = root / segment.relative_path
    _validate_file(root, path)
    before = path.stat()
    if before.st_size != segment.size_bytes or before.st_mtime_ns != segment.mtime_ns:
        raise FactsSegmentInventoryError('FACTS segment changed since inventory')
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    after = path.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise FactsSegmentInventoryError('FACTS segment changed during verification')
    if _load_cursor(root) != head:
        raise FactsSegmentInventoryError('FACTS publication cursor changed during verification')
    return VerifiedSealedFactsSegment(
        relative_path=segment.relative_path,
        size_bytes=after.st_size,
        sha256=digest.hexdigest(),
    )


def _validate_root(root: Path) -> None:
    if not isinstance(root, Path) or not root.is_absolute():
        raise ValueError('FACTS root must be an absolute Path')


def _validate_file(root: Path, path: Path) -> None:
    if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise FactsSegmentInventoryError('FACTS segment is not a regular local file')


@dataclass(frozen=True, slots=True)
class ArchivedFactsReceipt:
    relative_path: str
    size_bytes: int
    sha256: str
    remote_ref: str


def plan_facts_retirement_candidates(
    *,
    verified_segments: tuple[VerifiedSealedFactsSegment, ...],
    archive_receipts: tuple[ArchivedFactsReceipt, ...],
    required_consumer_positions: Mapping[str, FactsStreamPosition | None],
) -> tuple[VerifiedSealedFactsSegment, ...]:
    if not required_consumer_positions:
        return ()
    if not all(isinstance(name, str) and name.strip() for name in required_consumer_positions):
        raise ValueError('Required FACTS consumers must have non-empty names')
    if any(position is None for position in required_consumer_positions.values()):
        return ()
    if not all(
        isinstance(position, FactsStreamPosition)
        and isinstance(position.segment_path, str)
        and _SEGMENT_PATH.fullmatch(position.segment_path)
        for position in required_consumer_positions.values()
    ):
        raise TypeError('Required FACTS consumer positions must be valid FactsStreamPosition')
    receipts: dict[str, ArchivedFactsReceipt] = {}
    for receipt in archive_receipts:
        if not isinstance(receipt, ArchivedFactsReceipt):
            raise TypeError('Archive receipts must contain ArchivedFactsReceipt')
        if (
            not isinstance(receipt.relative_path, str)
            or _SEGMENT_PATH.fullmatch(receipt.relative_path) is None
            or not isinstance(receipt.size_bytes, int)
            or isinstance(receipt.size_bytes, bool)
            or receipt.size_bytes < 0
            or not isinstance(receipt.sha256, str)
            or re.fullmatch(r'[0-9a-f]{64}', receipt.sha256) is None
            or not isinstance(receipt.remote_ref, str)
            or not receipt.remote_ref.strip()
        ):
            raise ValueError('FACTS archive receipt is invalid')
        if receipt.relative_path in receipts:
            raise ValueError('Duplicate FACTS archive receipt')
        receipts[receipt.relative_path] = receipt
    oldest_cursor_path = min(
        position.segment_path for position in required_consumer_positions.values()
    )
    candidates: list[VerifiedSealedFactsSegment] = []
    for segment in verified_segments:
        if not isinstance(segment, VerifiedSealedFactsSegment):
            raise TypeError('Verified segments must contain VerifiedSealedFactsSegment')
        receipt = receipts.get(segment.relative_path)
        if (
            segment.relative_path < oldest_cursor_path
            and receipt is not None
            and receipt.size_bytes == segment.size_bytes
            and receipt.sha256 == segment.sha256
        ):
            candidates.append(segment)
    return tuple(sorted(candidates, key=lambda item: item.relative_path))
