from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import uuid4

from atlanticus.web.users.errors import UsersDefinitionError
from atlanticus.web.users.models import RuntimeUser
from atlanticus.web.users.store import UsersRuntimeStore


class UsersRecoveryError(RuntimeError):
    pass


class UsersRecoveryConflictError(UsersRecoveryError):
    pass


class UsersRecoveryUnavailableError(UsersRecoveryError):
    pass


class UserDifferenceKind(StrEnum):
    MISSING = 'missing'
    DIFFERENT = 'different'
    UNEXPECTED = 'unexpected'


_ID_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9-]{0,63}\Z')


def _required(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise UsersDefinitionError(f'{label} must be non-empty normalized text')
    return value


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or _ID_PATTERN.fullmatch(value) is None:
        raise UsersDefinitionError(f'{label} has an invalid format')
    return value


def _users_digest(users: tuple[RuntimeUser, ...]) -> str:
    document = {'users': [user.to_document() for user in users]}
    content = json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


@dataclass(frozen=True, slots=True)
class ToolUsersRecoverySnapshot:
    snapshot_id: str
    origin_environment: str
    captured_at_utc: str
    operator_id: str
    approval_reference: str
    users: tuple[RuntimeUser, ...]

    def __post_init__(self) -> None:
        _identifier(self.snapshot_id, 'Snapshot id')
        for name in (
            'origin_environment',
            'operator_id',
            'approval_reference',
        ):
            _required(getattr(self, name), name)
        try:
            captured = datetime.fromisoformat(self.captured_at_utc)
        except (TypeError, ValueError) as error:
            raise UsersDefinitionError('Snapshot timestamp is invalid') from error
        if captured.tzinfo is None or captured.utcoffset() is None:
            raise UsersDefinitionError('Snapshot timestamp requires a timezone')
        users = tuple(sorted(self.users, key=lambda user: user.user_id))
        if any(not isinstance(user, RuntimeUser) for user in users):
            raise UsersDefinitionError('Recovery snapshot contains invalid runtime users')
        user_ids = tuple(user.user_id for user in users)
        if len(user_ids) != len(set(user_ids)):
            raise UsersDefinitionError('Recovery snapshot user ids must be unique')
        object.__setattr__(self, 'users', users)

    @property
    def content_digest(self) -> str:
        return _users_digest(self.users)

    def to_document(self) -> dict[str, object]:
        document: dict[str, object] = {
            'document_type': 'atlanticus_tool_users_recovery_snapshot',
            'schema_version': 1,
            'snapshot_id': self.snapshot_id,
            'origin_environment': self.origin_environment,
            'captured_at_utc': self.captured_at_utc,
            'operator_id': self.operator_id,
            'approval_reference': self.approval_reference,
            'users': [user.to_document() for user in self.users],
            'content_digest': self.content_digest,
        }
        encoded = json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        document['artifact_digest'] = hashlib.sha256(encoded.encode('utf-8')).hexdigest()
        return document

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> ToolUsersRecoverySnapshot:
        try:
            if (
                document.get('document_type') != 'atlanticus_tool_users_recovery_snapshot'
                or document.get('schema_version') != 1
            ):
                raise TypeError
            raw_users = document['users']
            if not isinstance(raw_users, list) or any(not isinstance(item, dict) for item in raw_users):
                raise TypeError
            snapshot = cls(
                snapshot_id=_text(document, 'snapshot_id'),
                origin_environment=_text(document, 'origin_environment'),
                captured_at_utc=_text(document, 'captured_at_utc'),
                operator_id=_text(document, 'operator_id'),
                approval_reference=_text(document, 'approval_reference'),
                users=tuple(RuntimeUser.from_document(dict(item)) for item in raw_users),
            )
            if snapshot.to_document() != document:
                raise UsersDefinitionError('Recovery snapshot content or metadata does not match')
            return snapshot
        except (KeyError, TypeError, ValueError, UsersDefinitionError) as error:
            raise UsersDefinitionError('Recovery snapshot document is invalid') from error


@dataclass(frozen=True, slots=True)
class UsersCapturePreview:
    users: tuple[RuntimeUser, ...]
    content_digest: str

    @property
    def approved_users(self) -> tuple[RuntimeUser, ...]:
        return self.users

    @property
    def candidate_user_ids(self) -> tuple[str, ...]:
        return ()


@dataclass(frozen=True, slots=True)
class UserRecoveryDifference:
    user_id: str
    kind: UserDifferenceKind
    fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class UsersReplaceValidation:
    snapshot: ToolUsersRecoverySnapshot
    current_users: tuple[RuntimeUser, ...]
    differences: tuple[UserRecoveryDifference, ...]

    @property
    def can_replace(self) -> bool:
        return True

    @property
    def create_ids(self) -> tuple[str, ...]:
        return tuple(item.user_id for item in self.differences if item.kind is UserDifferenceKind.MISSING)

    @property
    def update_ids(self) -> tuple[str, ...]:
        return tuple(item.user_id for item in self.differences if item.kind is UserDifferenceKind.DIFFERENT)

    @property
    def delete_ids(self) -> tuple[str, ...]:
        return tuple(item.user_id for item in self.differences if item.kind is UserDifferenceKind.UNEXPECTED)


@dataclass(frozen=True, slots=True)
class UsersReplaceBeforeImage:
    operation_id: str
    snapshot_id: str
    captured_at_utc: str
    users: tuple[RuntimeUser, ...]

    def to_document(self) -> dict[str, object]:
        return {
            'document_type': 'atlanticus_tool_users_runtime_before_image',
            'schema_version': 1,
            'operation_id': self.operation_id,
            'snapshot_id': self.snapshot_id,
            'captured_at_utc': self.captured_at_utc,
            'users': [user.to_document() for user in self.users],
        }

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> UsersReplaceBeforeImage:
        try:
            raw_users = document['users']
            if (
                document.get('document_type') != 'atlanticus_tool_users_runtime_before_image'
                or document.get('schema_version') != 1
                or not isinstance(raw_users, list)
            ):
                raise TypeError
            return cls(
                operation_id=_text(document, 'operation_id'),
                snapshot_id=_text(document, 'snapshot_id'),
                captured_at_utc=_text(document, 'captured_at_utc'),
                users=tuple(RuntimeUser.from_document(item) for item in raw_users),
            )
        except (KeyError, TypeError, ValueError, UsersDefinitionError) as error:
            raise UsersDefinitionError('Users before-image document is invalid') from error


@dataclass(frozen=True, slots=True)
class UsersRecoveryAuditEvent:
    operation_id: str
    snapshot_id: str
    stage: str
    occurred_at_utc: str
    operator_id: str
    approval_reference: str
    detail: str | None = None

    def to_document(self) -> dict[str, object]:
        return {
            'document_type': 'atlanticus_tool_users_recovery_audit',
            'schema_version': 1,
            'operation_id': self.operation_id,
            'snapshot_id': self.snapshot_id,
            'stage': self.stage,
            'occurred_at_utc': self.occurred_at_utc,
            'operator_id': self.operator_id,
            'approval_reference': self.approval_reference,
            'detail': self.detail,
        }


class ToolUsersRecoverySnapshotStore(Protocol):
    def list_snapshot_ids(self, *, max_items: int = 200) -> tuple[str, ...]: ...
    def list_snapshot_summaries(
        self, *, max_items: int = 200
    ) -> tuple[tuple[str, str | None], ...]: ...
    def save(self, snapshot: ToolUsersRecoverySnapshot) -> None: ...
    def load(self, snapshot_id: str) -> ToolUsersRecoverySnapshot: ...


class UsersReplaceBeforeImageStore(Protocol):
    def save(self, image: UsersReplaceBeforeImage) -> None: ...


class UsersRecoveryAuditStore(Protocol):
    def record(self, event: UsersRecoveryAuditEvent) -> None: ...


class ToolUsersRecoveryService:
    def __init__(
        self,
        *,
        runtime: UsersRuntimeStore,
        materialize: Callable[[], tuple[RuntimeUser, ...]],
        snapshots: ToolUsersRecoverySnapshotStore,
        audit: UsersRecoveryAuditStore,
        before_images: UsersReplaceBeforeImageStore,
        environment: str,
    ) -> None:
        self._runtime = runtime
        self._materialize = materialize
        self._snapshots = snapshots
        self._audit = audit
        self._before_images = before_images
        self._environment = _required(environment, 'environment')

    def preview_capture(self) -> UsersCapturePreview:
        users = tuple(sorted(self._materialize(), key=lambda user: user.user_id))
        digest = _users_digest(users)
        return UsersCapturePreview(users=users, content_digest=digest)

    def capture(
        self,
        *,
        preview: UsersCapturePreview,
        approved_user_ids: tuple[str, ...],
        operator_id: str,
        approval_reference: str,
        confirmed: bool,
    ) -> ToolUsersRecoverySnapshot:
        if confirmed is not True:
            raise UsersRecoveryConflictError('Explicit snapshot confirmation is required')
        fresh = self.preview_capture()
        if fresh != preview:
            raise UsersRecoveryConflictError('Capture preview changed; review current state')
        if tuple(approved_user_ids) != tuple(user.user_id for user in fresh.users):
            raise UsersRecoveryConflictError('Recovery snapshot must include the complete Tool runtime')
        snapshot = ToolUsersRecoverySnapshot(
            snapshot_id=uuid4().hex,
            origin_environment=self._environment,
            captured_at_utc=datetime.now(UTC).isoformat(),
            operator_id=_required(operator_id, 'operator_id'),
            approval_reference=_required(approval_reference, 'approval_reference'),
            users=fresh.users,
        )
        self._snapshots.save(snapshot)
        return snapshot

    def validate_replace(self, snapshot_id: str) -> UsersReplaceValidation:
        snapshot = self._snapshots.load(snapshot_id)
        current = tuple(sorted(self._runtime.list_users(), key=lambda user: user.user_id))
        return UsersReplaceValidation(
            snapshot=snapshot,
            current_users=current,
            differences=_differences(current, snapshot.users),
        )

    def replace_snapshot(
        self,
        *,
        snapshot_id: str,
        operator_id: str,
        approval_reference: str,
        operation_id: str | None = None,
        confirmed: bool,
        maintenance_confirmed: bool,
        revocations_reviewed: bool,
    ) -> UsersReplaceValidation:
        if confirmed is not True or maintenance_confirmed is not True or revocations_reviewed is not True:
            raise UsersRecoveryConflictError('Recovery replacement requires explicit safety confirmation')
        validation = self.validate_replace(snapshot_id)
        operation = operation_id or uuid4().hex
        before = UsersReplaceBeforeImage(
            operation_id=operation,
            snapshot_id=snapshot_id,
            captured_at_utc=datetime.now(UTC).isoformat(),
            users=validation.current_users,
        )
        self._before_images.save(before)
        self._audit.record(
            UsersRecoveryAuditEvent(
                operation_id=operation,
                snapshot_id=snapshot_id,
                stage='started',
                occurred_at_utc=datetime.now(UTC).isoformat(),
                operator_id=_required(operator_id, 'operator_id'),
                approval_reference=_required(approval_reference, 'approval_reference'),
            )
        )
        try:
            self._runtime.replace_all(validation.snapshot.users)
            after = self.validate_replace(snapshot_id)
            if after.differences:
                raise UsersRecoveryConflictError('Users runtime does not match recovery snapshot')
        except Exception as error:
            self._audit.record(
                UsersRecoveryAuditEvent(
                    operation_id=operation,
                    snapshot_id=snapshot_id,
                    stage='failed',
                    occurred_at_utc=datetime.now(UTC).isoformat(),
                    operator_id=operator_id,
                    approval_reference=approval_reference,
                    detail=type(error).__name__,
                )
            )
            raise
        self._audit.record(
            UsersRecoveryAuditEvent(
                operation_id=operation,
                snapshot_id=snapshot_id,
                stage='completed',
                occurred_at_utc=datetime.now(UTC).isoformat(),
                operator_id=operator_id,
                approval_reference=approval_reference,
            )
        )
        return after

    def apply_snapshot(self, snapshot_id: str) -> UsersReplaceValidation:
        return self.replace_snapshot(
            snapshot_id=snapshot_id,
            operator_id='master-projection',
            approval_reference='master-projection',
            confirmed=True,
            maintenance_confirmed=True,
            revocations_reviewed=True,
        )



def _differences(
    current: tuple[RuntimeUser, ...],
    desired: tuple[RuntimeUser, ...],
) -> tuple[UserRecoveryDifference, ...]:
    current_by_id = {user.user_id: user for user in current}
    desired_by_id = {user.user_id: user for user in desired}
    result: list[UserRecoveryDifference] = []
    for user_id in sorted(set(current_by_id) | set(desired_by_id)):
        before = current_by_id.get(user_id)
        after = desired_by_id.get(user_id)
        if before is None:
            result.append(UserRecoveryDifference(user_id, UserDifferenceKind.MISSING))
        elif after is None:
            result.append(UserRecoveryDifference(user_id, UserDifferenceKind.UNEXPECTED))
        elif before != after:
            result.append(
                UserRecoveryDifference(
                    user_id,
                    UserDifferenceKind.DIFFERENT,
                    _runtime_fields(before, after),
                )
            )
    return tuple(result)


def _runtime_fields(before: RuntimeUser, after: RuntimeUser) -> tuple[str, ...]:
    fields = []
    if before.identity != after.identity:
        fields.append('identity')
    if before.enabled != after.enabled:
        fields.append('enabled')
    if before.profile != after.profile:
        fields.append('profile')
    if before.operational != after.operational:
        fields.append('operational')
    return tuple(fields)


def _text(document: dict[str, Any], key: str) -> str:
    value = document[key]
    if not isinstance(value, str):
        raise TypeError
    return value
