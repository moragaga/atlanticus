from __future__ import annotations

import json
import math
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from atlanticus.runtime._fence import PhysicalAuthorityFence
from atlanticus.runtime.errors import AtlanticusRuntimeError
from atlanticus.runtime.storage import resolve_runtime_root, validate_path_segment


@dataclass(frozen=True, slots=True)
class SuccessorIntent:
    run_id: str
    scheduled_at_utc: datetime
    requested_at_utc: datetime
    expires_at_utc: datetime


class SuccessorIntentStore:
    def __init__(
        self,
        *,
        volume_path: str | Path,
        application: str,
        job_key: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        segment = validate_path_segment(job_key, name='job_key')
        self._directory = resolve_runtime_root(volume_path, application=application) / 'successors'
        self._path = self._directory / f'{segment}.json'
        self._fence = PhysicalAuthorityFence(
            volume_path=volume_path,
            application=application,
            job_key=job_key,
        )
        if clock is not None and not callable(clock):
            raise TypeError('clock must be callable')
        self._clock = (lambda: datetime.now(UTC)) if clock is None else clock

    @property
    def path(self) -> Path:
        return self._path

    def announce(
        self,
        *,
        run_id: str,
        scheduled_at_utc: datetime,
        ttl_seconds: float,
    ) -> bool:
        _validate_run_id(run_id)
        _validate_utc(scheduled_at_utc, 'scheduled_at_utc')
        if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int | float):
            raise TypeError('ttl_seconds must be a number')
        if not math.isfinite(ttl_seconds) or ttl_seconds <= 0:
            raise ValueError('ttl_seconds must be finite and greater than zero')
        now = self._now()
        intent = SuccessorIntent(
            run_id=run_id,
            scheduled_at_utc=scheduled_at_utc,
            requested_at_utc=now,
            expires_at_utc=now + timedelta(seconds=ttl_seconds),
        )
        descriptor = self._acquire_fence()
        try:
            existing = self.read()
            if existing is not None:
                current_priority = (
                    existing.scheduled_at_utc,
                    existing.requested_at_utc,
                    existing.run_id,
                )
                proposed_priority = (
                    intent.scheduled_at_utc,
                    intent.requested_at_utc,
                    intent.run_id,
                )
                if existing.run_id == run_id and existing.scheduled_at_utc == scheduled_at_utc:
                    return True
                if proposed_priority <= current_priority:
                    return False
            self._write(intent)
            return True
        finally:
            self._fence.release(descriptor)

    def read(self) -> SuccessorIntent | None:
        try:
            payload = json.loads(self._path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return None
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise AtlanticusRuntimeError('Successor intent is unreadable') from error
        intent = _decode(payload)
        return intent if intent.expires_at_utc > self._now() else None

    def pending_for(
        self,
        *,
        run_id: str,
        scheduled_at_utc: datetime,
    ) -> SuccessorIntent | None:
        _validate_run_id(run_id)
        _validate_utc(scheduled_at_utc, 'scheduled_at_utc')
        intent = self.read()
        if (
            intent is None
            or intent.run_id == run_id
            or intent.scheduled_at_utc <= scheduled_at_utc
        ):
            return None
        return intent

    def clear(self, *, run_id: str) -> bool:
        _validate_run_id(run_id)
        descriptor = self._acquire_fence()
        try:
            intent = self.read()
            if intent is None or intent.run_id != run_id:
                return False
            try:
                self._path.unlink()
            except FileNotFoundError:
                return False
            _sync_directory(self._directory)
            return True
        finally:
            self._fence.release(descriptor)

    def _acquire_fence(self) -> int:
        descriptor = self._fence.acquire(wait_seconds=5.0, poll_seconds=0.05)
        if descriptor is None:
            raise AtlanticusRuntimeError('Successor authority fence is unavailable')
        return descriptor

    def _now(self) -> datetime:
        value = self._clock()
        _validate_utc(value, 'clock result')
        return value

    def _write(self, intent: SuccessorIntent) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        temporary = self._directory / f'.{self._path.name}.{uuid4().hex}.tmp'
        payload = {
            'schema_version': 1,
            'run_id': intent.run_id,
            'scheduled_at_utc': intent.scheduled_at_utc.isoformat(),
            'requested_at_utc': intent.requested_at_utc.isoformat(),
            'expires_at_utc': intent.expires_at_utc.isoformat(),
        }
        try:
            with os.fdopen(
                os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640),
                'w',
                encoding='utf-8',
            ) as stream:
                json.dump(payload, stream, separators=(',', ':'), sort_keys=True)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._path)
            _sync_directory(self._directory)
        finally:
            temporary.unlink(missing_ok=True)


def _decode(payload: object) -> SuccessorIntent:
    if (
        not isinstance(payload, dict)
        or set(payload) != {
            'schema_version', 'run_id', 'scheduled_at_utc',
            'requested_at_utc', 'expires_at_utc',
        }
        or type(payload['schema_version']) is not int
        or payload['schema_version'] != 1
    ):
        raise AtlanticusRuntimeError('Successor intent is invalid')
    run_id = payload['run_id']
    try:
        _validate_run_id(run_id)
        dates = tuple(
            datetime.fromisoformat(payload[key])
            for key in ('scheduled_at_utc', 'requested_at_utc', 'expires_at_utc')
        )
        for date in dates:
            _validate_utc(date, 'successor intent datetime')
    except (TypeError, ValueError, OverflowError) as error:
        raise AtlanticusRuntimeError('Successor intent is invalid') from error
    scheduled, requested, expires = dates
    if expires <= requested:
        raise AtlanticusRuntimeError('Successor intent is invalid')
    return SuccessorIntent(run_id, scheduled, requested, expires)


def _validate_run_id(value: str) -> None:
    if not isinstance(value, str):
        raise TypeError('run_id must be a string')
    if not value or not value.strip() or len(value) > 128:
        raise ValueError('run_id must be a nonempty string of at most 128 characters')


def _validate_utc(value: datetime, field: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f'{field} must be a datetime')
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f'{field} must be UTC')


def _sync_directory(directory: Path) -> None:
    if os.name == 'nt':
        return
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
