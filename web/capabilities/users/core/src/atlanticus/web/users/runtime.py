from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flask import has_request_context, session

from atlanticus.web.identity.access import AccessSnapshot
from atlanticus.web.users.errors import UsersContextError, UsersDefinitionError
from atlanticus.web.users.models import EffectiveUser
from atlanticus.web.users.profiles import ProfileDefinition

USERS_RUNTIME_SERVICE_KEY = 'atlanticus.web.users.runtime'
_SESSION_KEY = '_atlanticus_users_snapshot'


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
                'pending': self.user.pending,
                'avatar_text': self.user.avatar_text,
                'avatar_background_color': self.user.avatar_background_color,
                'avatar_text_color': self.user.avatar_text_color,
                'is_local': self.user.is_local,
                'profile': {
                    'key': self.user.profile.key,
                    'label': self.user.profile.label,
                    'background_color': self.user.profile.background_color,
                    'text_color': self.user.profile.text_color,
                },
            },
        }

    @classmethod
    def from_session(cls, value: object) -> UsersSnapshot:
        if not isinstance(value, dict):
            raise UsersContextError('Users snapshot is invalid')
        user_value = value.get('user')
        if not isinstance(user_value, dict):
            raise UsersContextError('Users snapshot user is invalid')
        profile_value = user_value.get('profile')
        if not isinstance(profile_value, dict):
            raise UsersContextError('Users snapshot profile is invalid')
        try:
            profile = ProfileDefinition(
                key=str(profile_value['key']),
                label=str(profile_value['label']),
                background_color=str(profile_value['background_color']),
                text_color=str(profile_value['text_color']),
            )
            user = EffectiveUser(
                user_id=str(user_value['user_id']),
                subject_id=str(user_value['subject_id']),
                display_name=str(user_value['display_name']),
                email=_optional_string(user_value.get('email')),
                enabled=bool(user_value['enabled']),
                pending=bool(user_value['pending']),
                avatar_text=str(user_value['avatar_text']),
                profile=profile,
                avatar_background_color=_optional_string(user_value.get('avatar_background_color')),
                avatar_text_color=_optional_string(user_value.get('avatar_text_color')),
                is_local=bool(user_value.get('is_local', False)),
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


def _require_request_context() -> None:
    if not has_request_context():
        raise UsersContextError('Users snapshot is only available inside a request')
