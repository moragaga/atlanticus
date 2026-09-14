from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flask import has_request_context, session

from atlanticus.web.identity.access import AccessSnapshot
from atlanticus.web.profiles.models import ProfileDefinition
from atlanticus.web.users.errors import UsersContextError, UsersDefinitionError
from atlanticus.web.users.models import EffectiveUser

USERS_RUNTIME_SERVICE_KEY = 'atlanticus.web.users.runtime'
# La clave v2 invalida limpiamente snapshots antiguos que serializaban Guest como Profile.
_SESSION_KEY = '_atlanticus_users_snapshot_v2'


@dataclass(frozen=True, slots=True)
class UsersSnapshot:
    load_id: str
    user: EffectiveUser

    def __post_init__(self) -> None:
        load_id = self.load_id.strip()
        if not load_id:
            raise UsersDefinitionError('Users snapshot load id must not be empty')
        object.__setattr__(self, 'load_id', load_id)

    # El snapshot conserva Profile sólo cuando existe; Pending se serializa explícitamente con profile=None.
    def to_session(self) -> dict[str, Any]:
        profile = self.user.profile
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
                'profile': (
                    None
                    if profile is None
                    else {
                        'key': profile.key,
                        'label': profile.label,
                        'background_color': profile.background_color,
                        'text_color': profile.text_color,
                    }
                ),
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
        try:
            # profile=None es válido únicamente si EffectiveUser valida después que el usuario es Pending.
            if profile_value is None:
                profile = None
            elif isinstance(profile_value, dict):
                profile = ProfileDefinition(
                    key=str(profile_value['key']),
                    label=str(profile_value['label']),
                    background_color=str(profile_value['background_color']),
                    text_color=str(profile_value['text_color']),
                )
            else:
                raise TypeError
            user = EffectiveUser(
                user_id=str(user_value['user_id']),
                subject_id=str(user_value['subject_id']),
                display_name=str(user_value['display_name']),
                email=_optional_string(user_value.get('email')),
                enabled=bool(user_value['enabled']),
                pending=bool(user_value['pending']),
                avatar_text=str(user_value['avatar_text']),
                profile=profile,
                # Pending recomputa sus colores estáticos y no reinterpreta valores persistidos como overrides.
                avatar_background_color=(
                    None
                    if bool(user_value['pending'])
                    else _optional_string(user_value.get('avatar_background_color'))
                ),
                avatar_text_color=(
                    None
                    if bool(user_value['pending'])
                    else _optional_string(user_value.get('avatar_text_color'))
                ),
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
