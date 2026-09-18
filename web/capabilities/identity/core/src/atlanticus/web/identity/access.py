from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from flask import has_request_context, session

from atlanticus.web.identity.errors import AccessContextError, IdentityDefinitionError
from atlanticus.web.identity.models import AuthenticatedIdentity

ACCESS_RUNTIME_SERVICE_KEY = 'atlanticus.web.identity.access'
_SESSION_KEY = '_atlanticus_access_snapshot_v2'


class AccessStatus(StrEnum):
    READY = 'ready'
    INVALID_IDENTITY = 'invalid_identity'
    USER_NOT_PROMOTED = 'user_not_promoted'
    USER_DISABLED = 'user_disabled'


@dataclass(frozen=True, slots=True)
class AccessDecision:
    status: AccessStatus
    user_id: str | None = None
    bootstrap_root: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.bootstrap_root, bool):
            raise IdentityDefinitionError('Access bootstrap root flag must be boolean')
        if self.status is AccessStatus.INVALID_IDENTITY:
            raise IdentityDefinitionError('Access resolver cannot return invalid identity')
        if self.user_id is not None:
            normalized = self.user_id.strip()
            object.__setattr__(self, 'user_id', normalized or None)
        if self.status in {AccessStatus.USER_NOT_PROMOTED, AccessStatus.USER_DISABLED}:
            if self.user_id is None:
                raise IdentityDefinitionError('Rejected user access decision requires user_id')
        if self.bootstrap_root and self.status is not AccessStatus.READY:
            raise IdentityDefinitionError('Bootstrap root access decision must be ready')
        if self.bootstrap_root and self.user_id is not None:
            raise IdentityDefinitionError('Bootstrap root access decision cannot contain user_id')


class AccessResolver(ABC):
    @abstractmethod
    def resolve(self, identity: AuthenticatedIdentity, *, load_id: str) -> AccessDecision:
        raise NotImplementedError


class AuthenticatedAccessResolver(AccessResolver):
    def resolve(self, identity: AuthenticatedIdentity, *, load_id: str) -> AccessDecision:
        del identity, load_id
        return AccessDecision(status=AccessStatus.READY)


@dataclass(frozen=True, slots=True)
class AccessSnapshot:
    load_id: str
    resolved_at_utc: str
    status: AccessStatus
    identity: AuthenticatedIdentity | None
    user_id: str | None = None
    bootstrap_root: bool = False

    def __post_init__(self) -> None:
        load_id = self.load_id.strip()
        if not load_id:
            raise IdentityDefinitionError('Access load id must not be empty')
        object.__setattr__(self, 'load_id', load_id)
        if not isinstance(self.bootstrap_root, bool):
            raise IdentityDefinitionError('Access bootstrap root flag must be boolean')
        if self.status is AccessStatus.INVALID_IDENTITY and self.identity is not None:
            raise IdentityDefinitionError('Invalid identity snapshot cannot contain identity')
        if self.status is not AccessStatus.INVALID_IDENTITY and self.identity is None:
            raise IdentityDefinitionError('Resolved access snapshot requires identity')
        if self.status in {AccessStatus.USER_NOT_PROMOTED, AccessStatus.USER_DISABLED}:
            if self.user_id is None:
                raise IdentityDefinitionError('Rejected user access snapshot requires user_id')
        if self.bootstrap_root and self.status is not AccessStatus.READY:
            raise IdentityDefinitionError('Bootstrap root access snapshot must be ready')
        if self.bootstrap_root and self.user_id is not None:
            raise IdentityDefinitionError('Bootstrap root access snapshot cannot contain user_id')

    @classmethod
    def resolved(
        cls,
        *,
        load_id: str,
        identity: AuthenticatedIdentity,
        decision: AccessDecision,
    ) -> AccessSnapshot:
        return cls(
            load_id=load_id,
            resolved_at_utc=datetime.now(UTC).isoformat(),
            status=decision.status,
            identity=identity,
            user_id=decision.user_id,
            bootstrap_root=decision.bootstrap_root,
        )

    @classmethod
    def invalid_identity(cls) -> AccessSnapshot:
        return cls(
            load_id=str(uuid4()),
            resolved_at_utc=datetime.now(UTC).isoformat(),
            status=AccessStatus.INVALID_IDENTITY,
            identity=None,
        )

    def to_session(self) -> dict[str, Any]:
        identity = None
        if self.identity is not None:
            identity = {
                'provider_key': self.identity.provider_key,
                'issuer': self.identity.issuer,
                'subject_id': self.identity.subject_id,
            }
        return {
            'load_id': self.load_id,
            'resolved_at_utc': self.resolved_at_utc,
            'status': self.status.value,
            'identity': identity,
            'user_id': self.user_id,
            'bootstrap_root': self.bootstrap_root,
        }

    @classmethod
    def from_session(cls, value: object) -> AccessSnapshot:
        if not isinstance(value, dict):
            raise AccessContextError('Access snapshot is invalid')
        identity_value = value.get('identity')
        identity = None
        if identity_value is not None:
            if not isinstance(identity_value, dict):
                raise AccessContextError('Access identity snapshot is invalid')
            try:
                identity = AuthenticatedIdentity(
                    provider_key=str(identity_value['provider_key']),
                    issuer=str(identity_value['issuer']),
                    subject_id=str(identity_value['subject_id']),
                )
            except (KeyError, IdentityDefinitionError) as error:
                raise AccessContextError('Access identity snapshot is invalid') from error
        try:
            bootstrap_root = value['bootstrap_root']
            if not isinstance(bootstrap_root, bool):
                raise TypeError
            return cls(
                load_id=str(value['load_id']),
                resolved_at_utc=str(value['resolved_at_utc']),
                status=AccessStatus(str(value['status'])),
                identity=identity,
                user_id=_optional_string(value.get('user_id')),
                bootstrap_root=bootstrap_root,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise AccessContextError('Access snapshot is invalid') from error


class AccessRuntime:
    def store(self, snapshot: AccessSnapshot) -> None:
        _require_request_context()
        session[_SESSION_KEY] = snapshot.to_session()

    def clear(self) -> None:
        _require_request_context()
        session.pop(_SESSION_KEY, None)

    def current(self) -> AccessSnapshot:
        snapshot = self.current_or_none()
        if snapshot is None:
            raise AccessContextError('Access snapshot is not available for this page load')
        return snapshot

    def current_or_none(self) -> AccessSnapshot | None:
        _require_request_context()
        value = session.get(_SESSION_KEY)
        if value is None:
            return None
        return AccessSnapshot.from_session(value)


def new_access_load_id() -> str:
    return str(uuid4())


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _require_request_context() -> None:
    if not has_request_context():
        raise AccessContextError('Access snapshot is only available inside a request')
