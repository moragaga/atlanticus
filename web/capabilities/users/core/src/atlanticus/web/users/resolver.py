from __future__ import annotations

from atlanticus.web.identity.access import AccessDecision, AccessResolver, AccessStatus
from atlanticus.web.identity.errors import AccessResolverUnavailableError
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.users.errors import (
    UsersDefinitionError,
    UsersIdentityConflictError,
    UsersStoreUnavailableError,
)
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import RuntimeUser
from atlanticus.web.users.runtime import UsersRuntime
from atlanticus.web.users.local import LOCAL_ISSUER
from atlanticus.web.users.store import UsersGuestObserver, UsersRuntimeStore


class UsersAccessResolver(AccessResolver):
    def __init__(
        self,
        *,
        store: UsersRuntimeStore,
        runtime: UsersRuntime,
        guest_observer: UsersGuestObserver | None = None,
    ) -> None:
        self._store = store
        self._runtime = runtime
        self._guest_observer = guest_observer

    def resolve(self, identity: AuthenticatedIdentity, *, load_id: str) -> AccessDecision:
        try:
            user = self._store.resolve(identity)
            if user is None:
                if self._guest_observer is None or identity.issuer == LOCAL_ISSUER:
                    return AccessDecision(
                        status=AccessStatus.READY,
                        user_id=build_user_key(issuer=identity.issuer, subject_id=identity.subject_id),
                    )
                user = self._guest_observer.observe_guest(identity)
            _require_runtime_identity(identity, user)
        except (
            UsersDefinitionError,
            UsersIdentityConflictError,
            UsersStoreUnavailableError,
        ) as error:
            raise AccessResolverUnavailableError('Users runtime store is unavailable') from error

        if not user.enabled:
            return AccessDecision(status=AccessStatus.USER_DISABLED, user_id=user.user_id)

        self._runtime.store(load_id=load_id, user=user)
        return AccessDecision(status=AccessStatus.READY, user_id=user.user_id)


def _require_runtime_identity(identity: AuthenticatedIdentity, user: RuntimeUser) -> None:
    expected_user_id = build_user_key(issuer=identity.issuer, subject_id=identity.subject_id)
    if (
        user.user_id != expected_user_id
        or user.issuer != identity.issuer
        or user.subject_id != identity.subject_id
    ):
        raise UsersIdentityConflictError('Runtime user does not match authenticated identity')
