# Espejo pedagógico: conserva exactamente el contrato productivo y explica su intención.
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flask import has_request_context, session

from atlanticus.web.identity.access import AccessSnapshot
from atlanticus.web.users.errors import UsersContextError, UsersDefinitionError
from atlanticus.web.users.models import EffectiveUser

USERS_RUNTIME_SERVICE_KEY = 'atlanticus.web.users.runtime'
_SESSION_KEY = '_atlanticus_users_snapshot_v3'


@dataclass(frozen=True, slots=True)
class UsersSnapshot:
    load_id: str
    user: EffectiveUser

    def __post_init__(self) -> None:
        load_id = self.load_id.strip()
        if not load_id:
            raise UsersDefinitionError('Users snapshot load id must not be empty')
        object.__setattr__(self, 'load_id', load_id)

    def to_session(self) -> dict[str, Any]:
        return {
            'load_id': self.load_id,
            'user': {
                'user_id': self.user.user_id,
                'subject_id': self.user.subject_id,
                'display_name': self.user.display_name,
                'email': self.user.email,
                'enabled': self.user.enabled,
                'avatar_text': self.user.avatar_text,
                'authority_key': self.user.authority_key,
                'avatar_background_color': self.user.avatar_background_color,
                'avatar_text_color': self.user.avatar_text_color,
                'is_local': self.user.is_local,
            },
        }

    @classmethod
    def from_session(cls, value: object) -> UsersSnapshot:
        if not isinstance(value, dict):
            raise UsersContextError('Users snapshot is invalid')
        user_value = value.get('user')
        if not isinstance(user_value, dict):
            raise UsersContextError('Users snapshot user is invalid')
        try:
            user = EffectiveUser(
                user_id=str(user_value['user_id']),
                subject_id=str(user_value['subject_id']),
                display_name=str(user_value['display_name']),
                email=_optional_string(user_value.get('email')),
                enabled=_required_bool(user_value, 'enabled'),
                avatar_text=str(user_value['avatar_text']),
                authority_key=str(user_value['authority_key']),
                avatar_background_color=_optional_string(
                    user_value.get('avatar_background_color')
                ),
                avatar_text_color=_optional_string(user_value.get('avatar_text_color')),
                is_local=_required_bool(user_value, 'is_local'),
            )
            return cls(load_id=str(value['load_id']), user=user)
        except (KeyError, TypeError, ValueError, UsersDefinitionError) as error:
            raise UsersContextError('Users snapshot is invalid') from error


class UsersRuntime:
    def store(self, *, load_id: str, user: EffectiveUser) -> None:
        _require_request_context()
        session[_SESSION_KEY] = UsersSnapshot(load_id=load_id, user=user).to_session()

    def current(self, access: AccessSnapshot) -> EffectiveUser:
        user = self.current_or_none(access)
        if user is None:
            raise UsersContextError('Effective user is not available for this page load')
        return user

    def current_or_none(self, access: AccessSnapshot) -> EffectiveUser | None:
        _require_request_context()
        value = session.get(_SESSION_KEY)
        if value is None:
            return None
        snapshot = UsersSnapshot.from_session(value)
        if snapshot.load_id != access.load_id:
            return None
        return snapshot.user


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _required_bool(document: dict[str, Any], key: str) -> bool:
    value = document[key]
    if not isinstance(value, bool):
        raise TypeError
    return value


def _require_request_context() -> None:
    if not has_request_context():
        raise UsersContextError('Users snapshot is only available inside a request')
