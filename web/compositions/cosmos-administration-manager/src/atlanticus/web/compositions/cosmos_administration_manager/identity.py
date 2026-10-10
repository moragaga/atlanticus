from __future__ import annotations

from collections.abc import Callable

from flask import has_request_context, request

from atlanticus.web.configuration import WebSettings
from atlanticus.web.identity.errors import IdentityAuthenticationError
from atlanticus.web.identity.provider import IdentityProvider
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.users.models import RuntimeUser
from atlanticus.web.users.store import UsersRuntimeStore


def create_authenticated_root_provider(
    *,
    identity_provider: IdentityProvider,
    users: UsersRuntimeStore,
) -> Callable[[], ManagerPrincipal | None]:
    if not isinstance(identity_provider, IdentityProvider):
        raise TypeError('Authenticated ROOT requires IdentityProvider')
    if not isinstance(users, UsersRuntimeStore):
        raise TypeError('Authenticated ROOT requires UsersRuntimeStore')

    def resolve() -> ManagerPrincipal | None:
        if not has_request_context():
            return None
        if WebSettings().environment.is_production and not identity_provider.production_ready:
            return None
        try:
            identity = identity_provider.resolve(request)
        except IdentityAuthenticationError:
            return None
        user = users.resolve(identity)
        if (
            not isinstance(user, RuntimeUser)
            or not user.enabled
            or user.issuer != identity.issuer
            or user.subject_id != identity.subject_id
            or not user.has_full_access
        ):
            return None
        if user.is_local and (
            identity.provider_key != 'local'
            or identity.issuer != 'atlanticus-local'
            or identity_provider.production_ready
            or WebSettings().environment.is_production
        ):
            return None
        return ManagerPrincipal(
            subject_id=user.user_id,
            display_name=user.display_name,
            profile_label='Local' if user.is_local else 'Root',
            is_local=user.is_local,
            administrative_override=True,
        )

    return resolve
