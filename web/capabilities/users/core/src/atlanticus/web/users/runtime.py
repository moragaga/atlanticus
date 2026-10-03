from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flask import has_request_context, session

from atlanticus.web.identity.access import AccessSnapshot
from atlanticus.web.users.errors import UsersContextError, UsersDefinitionError
from atlanticus.web.users.models import RuntimeUser

USERS_RUNTIME_SERVICE_KEY = 'atlanticus.web.users.runtime'
_SESSION_KEY = '_atlanticus_users_snapshot_v5'


@dataclass(frozen=True, slots=True)
class UsersSnapshot:
    load_id: str
    user: RuntimeUser

    def __post_init__(self) -> None:
        load_id = self.load_id.strip()
        if not load_id:
            raise UsersDefinitionError('Users snapshot load id must not be empty')
        object.__setattr__(self, 'load_id', load_id)

    def to_session(self) -> dict[str, Any]:
        return {'load_id': self.load_id, 'user': self.user.to_document()}

    @classmethod
    def from_session(cls, value: object) -> UsersSnapshot:
        if not isinstance(value, dict) or not isinstance(value.get('user'), dict):
            raise UsersContextError('Users snapshot is invalid')
        try:
            return cls(
                load_id=str(value['load_id']),
                user=RuntimeUser.from_document(value['user']),
            )
        except (KeyError, TypeError, ValueError, UsersDefinitionError) as error:
            raise UsersContextError('Users snapshot is invalid') from error


class UsersRuntime:
    def store(self, *, load_id: str, user: RuntimeUser) -> None:
        _require_request_context()
        if not isinstance(user, RuntimeUser):
            raise TypeError('Users runtime requires RuntimeUser')
        session[_SESSION_KEY] = UsersSnapshot(load_id=load_id, user=user).to_session()

    def current(self, access: AccessSnapshot) -> RuntimeUser:
        user = self.current_or_none(access)
        if user is None:
            raise UsersContextError('Runtime user is not available for this page load')
        return user

    def current_or_none(self, access: AccessSnapshot) -> RuntimeUser | None:
        _require_request_context()
        value = session.get(_SESSION_KEY)
        if value is None:
            return None
        snapshot = UsersSnapshot.from_session(value)
        if snapshot.load_id != access.load_id:
            return None
        return snapshot.user


def _require_request_context() -> None:
    if not has_request_context():
        raise UsersContextError('Users snapshot is only available inside a request')
