from __future__ import annotations

import hashlib

from atlanticus.web.identity.access import AccessDecision, AccessResolver, AccessStatus
from atlanticus.web.identity.errors import AccessResolverUnavailableError
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.users.errors import UsersIdentityConflictError, UsersSourceUnavailableError
from atlanticus.web.users.models import EffectiveUser, build_avatar_text
from atlanticus.web.users.profiles import GUEST_PROFILE_KEY, ProfileCatalog
from atlanticus.web.users.runtime import UsersRuntime
from atlanticus.web.users.source import UsersSource


class UsersAccessResolver(AccessResolver):
    def __init__(
        self,
        *,
        source: UsersSource,
        runtime: UsersRuntime,
        profiles: ProfileCatalog,
    ) -> None:
        self._source = source
        self._runtime = runtime
        self._profiles = profiles

    def resolve(self, identity: AuthenticatedIdentity, *, load_id: str) -> AccessDecision:
        try:
            record = self._source.resolve(identity)
        except (UsersSourceUnavailableError, UsersIdentityConflictError) as error:
            raise AccessResolverUnavailableError('Users source is unavailable') from error

        if record is None:
            user = self._pending_guest(identity)
        else:
            profile = self._profiles.require(record.profile_key)
            user = record.to_effective_user(profile=profile)
        self._runtime.store(load_id=load_id, user=user)
        if not user.enabled:
            return AccessDecision(status=AccessStatus.USER_DISABLED, user_id=user.user_id)
        return AccessDecision(status=AccessStatus.READY, user_id=user.user_id)

    def _pending_guest(self, identity: AuthenticatedIdentity) -> EffectiveUser:
        display_name = identity.display_name or identity.email or 'Usuario pendiente'
        return EffectiveUser(
            user_id=_pending_user_id(identity),
            subject_id=identity.subject_id,
            display_name=display_name,
            email=identity.email,
            enabled=True,
            pending=True,
            avatar_text=build_avatar_text(display_name),
            profile=self._profiles.require(GUEST_PROFILE_KEY),
            avatar_background_color=None,
            avatar_text_color=None,
            is_local=False,
        )


def _pending_user_id(identity: AuthenticatedIdentity) -> str:
    material = f'{identity.provider_key}|{identity.issuer}|{identity.subject_id}'.encode()
    digest = hashlib.sha256(material).hexdigest()[:24]
    return f'pending:{digest}'
