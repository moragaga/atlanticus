from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import uuid4

from atlanticus.web.users.errors import UsersDefinitionError
from atlanticus.web.users.models import UserRecord, UsersRegistrySnapshot
from atlanticus.web.users.profiles import (
    UsersProfileCatalogProvider,
    require_managed_profile,
    resolve_profile_catalog,
)
from atlanticus.web.users.store import UsersAdministrationStore, UsersRegistryStore


class UsersRecoveryError(RuntimeError):
    pass


class UsersRecoveryConflictError(UsersRecoveryError):
    pass


class UsersRecoveryUnavailableError(UsersRecoveryError):
    pass


class UserDifferenceKind(StrEnum):
    MISSING = 'missing'
    DIFFERENT = 'different'
    IDENTITY_CONFLICT = 'identity_conflict'
    UNEXPECTED = 'unexpected'
    PROFILE_UNAVAILABLE = 'profile_unavailable'


class RegistryRecoveryState(StrEnum):
    EMPTY = 'empty'
    MATCH = 'match'
    CONFLICT = 'conflict'


_USER_FIELDS = (
    'issuer',
    'subject_id',
    'display_name',
    'email',
    'enabled',
    'profile_key',
    'avatar_background_color',
    'avatar_text_color',
)
_ID_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9-]{0,63}\Z')


def _required(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise UsersDefinitionError(f'{label} must be non-empty normalized text')
    return value


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or _ID_PATTERN.fullmatch(value) is None:
        raise UsersDefinitionError(f'{label} has an invalid format')
    return value


def _users_digest(
    application_key: str,
    identity_realm: str,
    users: tuple[UserRecord, ...],
) -> str:
    document = {
        'application_key': application_key,
        'identity_realm': identity_realm,
        'users': [user.to_document() for user in users],
    }
    content = json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


@dataclass(frozen=True, slots=True)
class ApprovedUsersSnapshot:
    snapshot_id: str
    application_key: str
    identity_realm: str
    origin_environment: str
    captured_at_utc: str
    operator_id: str
    approval_reference: str
    users: tuple[UserRecord, ...]
    source_registry_version: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.snapshot_id, 'Snapshot id')
        for name in (
            'application_key',
            'identity_realm',
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
        if self.source_registry_version is not None:
            _required(self.source_registry_version, 'source_registry_version')
        if not self.users:
            raise UsersDefinitionError('Approved snapshot must not be empty')
        normalized = UsersRegistrySnapshot(users=tuple(self.users)).users
        if any(user.profile_key in {'guest', 'local'} for user in normalized):
            raise UsersDefinitionError('Approved snapshot contains an unmanaged profile')
        object.__setattr__(self, 'users', normalized)

    @property
    def content_digest(self) -> str:
        return _users_digest(self.application_key, self.identity_realm, self.users)

    def to_document(self) -> dict[str, object]:
        document: dict[str, object] = {
            'document_type': 'atlanticus_approved_users_snapshot',
            'schema_version': 1,
            'snapshot_id': self.snapshot_id,
            'application_key': self.application_key,
            'identity_realm': self.identity_realm,
            'origin_environment': self.origin_environment,
            'captured_at_utc': self.captured_at_utc,
            'operator_id': self.operator_id,
            'approval_reference': self.approval_reference,
            'source_registry_version': self.source_registry_version,
            'users': [user.to_document() for user in self.users],
            'content_digest': self.content_digest,
        }
        encoded = json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        document['artifact_digest'] = hashlib.sha256(encoded.encode('utf-8')).hexdigest()
        return document

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> ApprovedUsersSnapshot:
        try:
            if (
                not isinstance(document, dict)
                or document.get('document_type') != 'atlanticus_approved_users_snapshot'
                or type(document.get('schema_version')) is not int
                or document['schema_version'] != 1
            ):
                raise TypeError
            raw_users = document['users']
            if not isinstance(raw_users, list) or any(
                not isinstance(item, dict) for item in raw_users
            ):
                raise TypeError
            fields = (
                'snapshot_id',
                'application_key',
                'identity_realm',
                'origin_environment',
                'captured_at_utc',
                'operator_id',
                'approval_reference',
                'content_digest',
                'artifact_digest',
            )
            if any(not isinstance(document[key], str) for key in fields):
                raise TypeError
            if document['source_registry_version'] is not None and not isinstance(
                document['source_registry_version'], str
            ):
                raise TypeError
            snapshot = cls(
                snapshot_id=document['snapshot_id'],
                application_key=document['application_key'],
                identity_realm=document['identity_realm'],
                origin_environment=document['origin_environment'],
                captured_at_utc=document['captured_at_utc'],
                operator_id=document['operator_id'],
                approval_reference=document['approval_reference'],
                source_registry_version=document['source_registry_version'],
                users=tuple(UserRecord.from_document(user) for user in raw_users),
            )
            if snapshot.to_document() != document:
                raise UsersDefinitionError('Approved snapshot content or metadata does not match')
            return snapshot
        except (KeyError, TypeError, ValueError) as error:
            raise UsersDefinitionError('Approved snapshot document is invalid') from error


@dataclass(frozen=True, slots=True)
class UsersCapturePreview:
    registry_version: str | None
    approved_users: tuple[UserRecord, ...]
    candidate_user_ids: tuple[str, ...]
    content_digest: str


@dataclass(frozen=True, slots=True)
class UserRecoveryDifference:
    user_id: str
    kind: UserDifferenceKind
    fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class UsersRecoveryValidation:
    snapshot: ApprovedUsersSnapshot
    registry_version: str | None
    registry_state: RegistryRecoveryState
    registry_conflict_user_ids: tuple[str, ...]
    differences: tuple[UserRecoveryDifference, ...]

    @property
    def can_restore(self) -> bool:
        return self.registry_state is not RegistryRecoveryState.CONFLICT and all(
            item.kind is UserDifferenceKind.MISSING for item in self.differences
        )


@dataclass(frozen=True, slots=True)
class UsersRecoveryAuditEvent:
    operation_id: str
    stage: str
    snapshot_id: str
    snapshot_digest: str
    target_environment: str
    operator_id: str
    approval_reference: str
    at_utc: str
    created_user_ids: tuple[str, ...] = ()
    error_type: str | None = None

    def to_document(self) -> dict[str, object]:
        return {
            'document_type': 'atlanticus_users_recovery_audit',
            'schema_version': 1,
            'operation_id': self.operation_id,
            'stage': self.stage,
            'snapshot_id': self.snapshot_id,
            'snapshot_digest': self.snapshot_digest,
            'target_environment': self.target_environment,
            'operator_id': self.operator_id,
            'approval_reference': self.approval_reference,
            'at_utc': self.at_utc,
            'created_user_ids': list(self.created_user_ids),
            'error_type': self.error_type,
        }


class ApprovedUsersSnapshotStore(Protocol):
    def save(self, snapshot: ApprovedUsersSnapshot) -> None: ...

    def load(self, snapshot_id: str) -> ApprovedUsersSnapshot: ...


class UsersRecoveryAuditStore(Protocol):
    def record(self, event: UsersRecoveryAuditEvent) -> None: ...


class UsersApprovedRecoveryService:
    def __init__(
        self,
        *,
        registry: UsersRegistryStore,
        promoted: UsersAdministrationStore,
        profiles: UsersProfileCatalogProvider,
        snapshots: ApprovedUsersSnapshotStore,
        application_key: str,
        identity_realm: str,
        environment: str,
        audit: UsersRecoveryAuditStore | None = None,
    ) -> None:
        self._registry = registry
        self._promoted = promoted
        self._profiles = profiles
        self._snapshots = snapshots
        self._audit = audit
        self._application_key = _required(application_key, 'application_key')
        self._identity_realm = _required(identity_realm, 'identity_realm')
        self._environment = _required(environment, 'environment')

    def preview_capture(self) -> UsersCapturePreview:
        registry = self._registry.load()
        promoted = UsersRegistrySnapshot(users=self._promoted.list_users()).users
        if not promoted:
            raise UsersRecoveryConflictError('No promoted users are available for approval')
        catalog = resolve_profile_catalog(self._profiles)
        for user in promoted:
            if registry.get(user.user_id) != user:
                raise UsersRecoveryConflictError('Promoted user differs from durable registry')
            try:
                require_managed_profile(user.profile_key, profiles=catalog)
            except UsersDefinitionError as error:
                raise UsersRecoveryConflictError('Promoted user profile is invalid') from error
        approved_ids = {user.user_id for user in promoted}
        return UsersCapturePreview(
            registry_version=registry.version,
            approved_users=promoted,
            candidate_user_ids=tuple(
                user.user_id for user in registry.users if user.user_id not in approved_ids
            ),
            content_digest=_users_digest(self._application_key, self._identity_realm, promoted),
        )

    def capture(
        self,
        *,
        preview: UsersCapturePreview,
        approved_user_ids: tuple[str, ...],
        operator_id: str,
        approval_reference: str,
        confirmed: bool,
    ) -> ApprovedUsersSnapshot:
        if confirmed is not True:
            raise UsersRecoveryConflictError('Explicit capture confirmation is required')
        _required(operator_id, 'operator_id')
        _required(approval_reference, 'approval_reference')
        current = self.preview_capture()
        if not isinstance(preview, UsersCapturePreview) or preview != current:
            raise UsersRecoveryConflictError('Capture preview is outdated')
        actual_ids = tuple(user.user_id for user in current.approved_users)
        if tuple(sorted(approved_user_ids)) != actual_ids:
            raise UsersRecoveryConflictError('Selected approved users do not match capture preview')
        snapshot = ApprovedUsersSnapshot(
            snapshot_id=uuid4().hex,
            application_key=self._application_key,
            identity_realm=self._identity_realm,
            origin_environment=self._environment,
            captured_at_utc=datetime.now(UTC).isoformat(),
            operator_id=operator_id,
            approval_reference=approval_reference,
            source_registry_version=current.registry_version,
            users=current.approved_users,
        )
        self._snapshots.save(snapshot)
        return snapshot

    def validate(self, snapshot_id: str) -> UsersRecoveryValidation:
        snapshot = self._snapshots.load(_identifier(snapshot_id, 'Snapshot id'))
        if (
            snapshot.application_key != self._application_key
            or snapshot.identity_realm != self._identity_realm
        ):
            raise UsersRecoveryConflictError(
                'Snapshot application or identity realm is incompatible'
            )
        catalog = resolve_profile_catalog(self._profiles)
        registry = self._registry.load()
        actual_users = UsersRegistrySnapshot(users=self._promoted.list_users()).users
        expected = {user.user_id: user for user in snapshot.users}
        actual = {user.user_id: user for user in actual_users}
        differences: list[UserRecoveryDifference] = []
        for user_id, user in expected.items():
            try:
                require_managed_profile(user.profile_key, profiles=catalog)
            except UsersDefinitionError:
                differences.append(
                    UserRecoveryDifference(user_id, UserDifferenceKind.PROFILE_UNAVAILABLE)
                )
            existing = actual.get(user_id)
            if existing is None:
                differences.append(UserRecoveryDifference(user_id, UserDifferenceKind.MISSING))
            elif (existing.issuer, existing.subject_id) != (user.issuer, user.subject_id):
                differences.append(
                    UserRecoveryDifference(user_id, UserDifferenceKind.IDENTITY_CONFLICT)
                )
            elif existing != user:
                differences.append(
                    UserRecoveryDifference(
                        user_id,
                        UserDifferenceKind.DIFFERENT,
                        tuple(
                            field
                            for field in _USER_FIELDS
                            if getattr(user, field) != getattr(existing, field)
                        ),
                    )
                )
        for user_id in sorted(set(actual) - set(expected)):
            differences.append(UserRecoveryDifference(user_id, UserDifferenceKind.UNEXPECTED))
        if registry.users == snapshot.users:
            registry_state = RegistryRecoveryState.MATCH
        elif not registry.users:
            registry_state = RegistryRecoveryState.EMPTY
        else:
            registry_state = RegistryRecoveryState.CONFLICT
        registry_expected = {user.user_id: user for user in registry.users}
        registry_conflicts = (
            tuple(
                sorted(
                    user_id
                    for user_id in set(registry_expected) | set(expected)
                    if registry_expected.get(user_id) != expected.get(user_id)
                )
            )
            if registry_state is RegistryRecoveryState.CONFLICT
            else ()
        )
        return UsersRecoveryValidation(
            snapshot=snapshot,
            registry_version=registry.version,
            registry_state=registry_state,
            registry_conflict_user_ids=registry_conflicts,
            differences=tuple(sorted(differences, key=lambda item: (item.user_id, item.kind))),
        )

    def restore(
        self,
        *,
        validation: UsersRecoveryValidation,
        confirmed_digest: str,
        operator_id: str,
        approval_reference: str,
        operation_id: str,
        confirmed: bool,
        maintenance_confirmed: bool,
    ) -> UsersRecoveryValidation:
        if confirmed is not True or maintenance_confirmed is not True:
            raise UsersRecoveryConflictError(
                'Explicit restore and maintenance confirmation is required'
            )
        _required(operator_id, 'operator_id')
        _required(approval_reference, 'approval_reference')
        _identifier(operation_id, 'Operation id')
        if not isinstance(validation, UsersRecoveryValidation):
            raise UsersRecoveryConflictError('Recovery validation is required')
        current = self.validate(validation.snapshot.snapshot_id)
        if current != validation or current.snapshot.content_digest != confirmed_digest:
            raise UsersRecoveryConflictError('Recovery validation or snapshot changed')
        if not current.can_restore:
            raise UsersRecoveryConflictError('Recovery target is not empty or prepared')
        audit = self._audit
        if audit is None:
            raise UsersRecoveryConflictError('Recovery audit store is required')
        event_data = {
            'operation_id': operation_id,
            'snapshot_id': current.snapshot.snapshot_id,
            'snapshot_digest': current.snapshot.content_digest,
            'target_environment': self._environment,
            'operator_id': operator_id,
            'approval_reference': approval_reference,
        }
        audit.record(
            UsersRecoveryAuditEvent(
                stage='started', at_utc=datetime.now(UTC).isoformat(), **event_data
            )
        )
        created: list[str] = []
        expected_users = {user.user_id: user for user in current.snapshot.users}
        try:
            if current.registry_state is RegistryRecoveryState.EMPTY:
                persisted = self._registry.replace(
                    current.snapshot.users,
                    expected_version=current.registry_version,
                )
                if persisted.users != current.snapshot.users:
                    raise UsersRecoveryUnavailableError('Target registry persisted different users')
            for difference in current.differences:
                if difference.kind is UserDifferenceKind.MISSING:
                    user = expected_users[difference.user_id]
                    persisted_user = self._promoted.create(user)
                    if persisted_user != user:
                        raise UsersRecoveryUnavailableError(
                            'Target store persisted a different user'
                        )
                    created.append(user.user_id)
            after = self.validate(current.snapshot.snapshot_id)
            if after.registry_state is not RegistryRecoveryState.MATCH or after.differences:
                raise UsersRecoveryConflictError('Recovery target changed during restore')
            audit.record(
                UsersRecoveryAuditEvent(
                    stage='completed',
                    at_utc=datetime.now(UTC).isoformat(),
                    created_user_ids=tuple(created),
                    **event_data,
                )
            )
            return after
        except Exception as error:
            try:
                audit.record(
                    UsersRecoveryAuditEvent(
                        stage='failed',
                        at_utc=datetime.now(UTC).isoformat(),
                        created_user_ids=tuple(created),
                        error_type=type(error).__name__,
                        **event_data,
                    )
                )
            except Exception as audit_error:
                raise UsersRecoveryUnavailableError(
                    'Recovery failed and failure audit was not saved'
                ) from audit_error
            raise
