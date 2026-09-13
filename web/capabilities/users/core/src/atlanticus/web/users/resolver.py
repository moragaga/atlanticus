from __future__ import annotations

from atlanticus.web.identity.access import AccessDecision, AccessResolver, AccessStatus
from atlanticus.web.identity.errors import AccessResolverUnavailableError
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.users.errors import (
    UsersDefinitionError,
    UsersIdentityConflictError,
    UsersRuntimeStoreUnavailableError,
)
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import PendingUserRecord, RuntimeUserRecord
from atlanticus.web.users.profiles import GUEST_PROFILE_KEY, ProfileCatalog
from atlanticus.web.users.runtime import UsersRuntime
from atlanticus.web.users.store import UsersRuntimeStore


class UsersAccessResolver(AccessResolver):
    def __init__(
        self,
        *,
        store: UsersRuntimeStore,
        runtime: UsersRuntime,
        profiles: ProfileCatalog,
    ) -> None:
        self._store = store
        self._runtime = runtime
        self._profiles = profiles

    def resolve(self, identity: AuthenticatedIdentity, *, load_id: str) -> AccessDecision:
        try:
            record = self._store.resolve(identity)
            if record is None:
                record = self._store.observe(identity)
            _require_runtime_identity(identity, record)
        except (
            UsersDefinitionError,
            UsersIdentityConflictError,
            UsersRuntimeStoreUnavailableError,
        ) as error:
            raise AccessResolverUnavailableError('Users runtime store is unavailable') from error

        if isinstance(record, PendingUserRecord):
            user = record.to_effective_user(
                profile=self._profiles.require(GUEST_PROFILE_KEY),
            )
        else:
            profile = self._profiles.require(record.profile_key)
            user = record.to_effective_user(profile=profile)

        self._runtime.store(load_id=load_id, user=user)
        if not user.enabled:
            return AccessDecision(status=AccessStatus.USER_DISABLED, user_id=user.user_id)
        return AccessDecision(status=AccessStatus.READY, user_id=user.user_id)


def _require_runtime_identity(
    identity: AuthenticatedIdentity,
    record: RuntimeUserRecord,
) -> None:
    expected_user_id = build_user_key(
        issuer=identity.issuer,
        subject_id=identity.subject_id,
    )
    if (
        record.user_id != expected_user_id
        or record.issuer != identity.issuer
        or record.subject_id != identity.subject_id
    ):
        raise UsersIdentityConflictError('Runtime user does not match authenticated identity')
