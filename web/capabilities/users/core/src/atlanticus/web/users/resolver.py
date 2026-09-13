from __future__ import annotations

from atlanticus.web.identity.access import AccessDecision, AccessResolver, AccessStatus
from atlanticus.web.identity.errors import AccessResolverUnavailableError
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.users.errors import UsersIdentityConflictError, UsersSourceUnavailableError
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import EffectiveUser, ResolvedUserRecord, build_avatar_text
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
            if record is not None:
                _require_resolved_identity(identity, record)
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
            user_id=build_user_key(
                issuer=identity.issuer,
                subject_id=identity.subject_id,
            ),
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


def _require_resolved_identity(
    identity: AuthenticatedIdentity,
    record: ResolvedUserRecord,
) -> None:
    expected_user_id = build_user_key(
        issuer=identity.issuer,
        subject_id=identity.subject_id,
    )
    if (
        record.user_id != expected_user_id
        or record.subject_id.strip() != identity.subject_id.strip()
    ):
        raise UsersIdentityConflictError('Resolved user does not match authenticated identity')
