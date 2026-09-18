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
from atlanticus.web.users.models import UserRecord
from atlanticus.web.users.runtime import UsersRuntime
from atlanticus.web.users.store import UsersRuntimeStore


class UsersAccessResolver(AccessResolver):
    def __init__(self, *, store: UsersRuntimeStore, runtime: UsersRuntime) -> None:
        self._store = store
        self._runtime = runtime

    def resolve(self, identity: AuthenticatedIdentity, *, load_id: str) -> AccessDecision:
        try:
            record = self._store.resolve(identity)
            if record is None:
                return AccessDecision(
                    status=AccessStatus.USER_NOT_PROMOTED,
                    user_id=build_user_key(issuer=identity.issuer, subject_id=identity.subject_id),
                )
            _require_runtime_identity(identity, record)
        except (
            UsersDefinitionError,
            UsersIdentityConflictError,
            UsersStoreUnavailableError,
        ) as error:
            raise AccessResolverUnavailableError('Users runtime store is unavailable') from error

        if not record.enabled:
            return AccessDecision(status=AccessStatus.USER_DISABLED, user_id=record.user_id)

        user = record.to_effective_user()
        self._runtime.store(load_id=load_id, user=user)
        return AccessDecision(status=AccessStatus.READY, user_id=user.user_id)


def _require_runtime_identity(identity: AuthenticatedIdentity, record: UserRecord) -> None:
    expected_user_id = build_user_key(issuer=identity.issuer, subject_id=identity.subject_id)
    if (
        record.user_id != expected_user_id
        or record.issuer != identity.issuer
        or record.subject_id != identity.subject_id
    ):
        raise UsersIdentityConflictError('Runtime user does not match authenticated identity')
