from __future__ import annotations

import hmac
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from flask import current_app, has_request_context, session

from atlanticus.web.deployment_access import (
    DeploymentAccessService,
    MaterialAvailability,
)

_SESSION_KEY = '_atlanticus_deployment_root_manager_v1'
_FINGERPRINT = re.compile(r'[0-9a-f]{64}\Z')
_MATERIAL_ID = re.compile(r'[0-9a-f]{32}\Z')


class DeploymentRootSessionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DeploymentRootSessionIdentity:
    material_id: str
    service_user: str
    fingerprint: str
    expires_at_epoch: int


class DeploymentRootSession:
    def __init__(
        self,
        *,
        access: DeploymentAccessService,
        ttl_seconds: int = 1800,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(access, DeploymentAccessService):
            raise TypeError('Root session requires DeploymentAccessService')
        if (
            not isinstance(ttl_seconds, int)
            or isinstance(ttl_seconds, bool)
            or not 1 <= ttl_seconds <= 86400
        ):
            raise ValueError('Root session lifetime must be between 1 and 86400 seconds')
        if clock is not None and not callable(clock):
            raise TypeError('Root session clock must be callable')
        self._access = access
        self._ttl_seconds = ttl_seconds
        self._clock = clock or (lambda: datetime.now(UTC))

    def login(self, *, service_user: str, password: str) -> DeploymentRootSessionIdentity:
        store = _session()
        store.pop(_SESSION_KEY, None)
        authenticated = self._access.authenticate(service_user=service_user, password=password)
        if authenticated.identity.access_level != 'manager.root':
            raise DeploymentRootSessionError('Deployment access has an invalid access level')
        current = self._access.inspect()
        if (
            current.availability is not MaterialAvailability.PRESENT
            or current.fingerprint is None
            or not hmac.compare_digest(current.fingerprint, authenticated.fingerprint)
        ):
            raise DeploymentRootSessionError('Deployment access material changed during login')
        now = self._epoch()
        identity = DeploymentRootSessionIdentity(
            material_id=authenticated.identity.material_id,
            service_user=authenticated.identity.service_user,
            fingerprint=authenticated.fingerprint,
            expires_at_epoch=now + self._ttl_seconds,
        )
        store[_SESSION_KEY] = {
            'material_id': identity.material_id,
            'service_user': identity.service_user,
            'fingerprint': identity.fingerprint,
            'issued_at_epoch': now,
            'expires_at_epoch': identity.expires_at_epoch,
        }
        return identity

    def current(self) -> DeploymentRootSessionIdentity | None:
        store = _session()
        raw = store.get(_SESSION_KEY)
        if raw is None:
            return None
        if not _valid_claims(raw):
            store.pop(_SESSION_KEY, None)
            return None
        now = self._epoch()
        if (
            raw['issued_at_epoch'] > now
            or raw['expires_at_epoch'] <= now
            or raw['expires_at_epoch'] - raw['issued_at_epoch'] > self._ttl_seconds
        ):
            store.pop(_SESSION_KEY, None)
            return None
        state = self._access.inspect()
        if (
            state.availability is not MaterialAvailability.PRESENT
            or state.fingerprint is None
            or not hmac.compare_digest(state.fingerprint, raw['fingerprint'])
        ):
            store.pop(_SESSION_KEY, None)
            return None
        return DeploymentRootSessionIdentity(
            material_id=raw['material_id'],
            service_user=raw['service_user'],
            fingerprint=raw['fingerprint'],
            expires_at_epoch=raw['expires_at_epoch'],
        )

    def logout(self) -> None:
        _session().pop(_SESSION_KEY, None)

    def _epoch(self) -> int:
        value = self._clock()
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise DeploymentRootSessionError('Root session clock must return an aware datetime')
        return int(value.timestamp())


def _valid_claims(value: object) -> bool:
    if not isinstance(value, dict) or set(value) != {
        'material_id',
        'service_user',
        'fingerprint',
        'issued_at_epoch',
        'expires_at_epoch',
    }:
        return False
    material = value['material_id']
    user = value['service_user']
    fingerprint = value['fingerprint']
    issued = value['issued_at_epoch']
    expires = value['expires_at_epoch']
    return (
        isinstance(material, str)
        and _MATERIAL_ID.fullmatch(material) is not None
        and isinstance(user, str)
        and bool(user)
        and user == user.strip()
        and len(user) <= 128
        and isinstance(fingerprint, str)
        and _FINGERPRINT.fullmatch(fingerprint) is not None
        and type(issued) is int
        and type(expires) is int
        and issued >= 0
        and expires > issued
    )


def _session():
    if not has_request_context():
        raise DeploymentRootSessionError('Root session requires a Flask request')
    if not current_app.secret_key:
        raise DeploymentRootSessionError('Root session requires a configured Flask secret key')
    return session
