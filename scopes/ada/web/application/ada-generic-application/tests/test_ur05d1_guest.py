from __future__ import annotations

from ada.web.application.generic.manager.principal import resolve_manager_principal
from ada.web.application.generic.navigation_binding import (
    manager_navigation_principal,
    public_navigation_principal,
)
from atlanticus.web.identity.access import AccessDecision, AccessSnapshot, AccessStatus
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.navigation.access import can_open_navigation_access
from atlanticus.web.profiles.models import GUEST_PROFILE_KEY


def _access(*, bootstrap_root=False):
    identity = AuthenticatedIdentity(provider_key='entra', issuer='issuer', subject_id='operator')
    return AccessSnapshot.resolved(
        load_id='load', identity=identity,
        decision=AccessDecision(status=AccessStatus.READY, bootstrap_root=bootstrap_root),
    )


def test_authenticated_unmanaged_user_receives_guest_navigation():
    principal = resolve_manager_principal(access=_access(), user=None)
    assert principal.profile_keys == (GUEST_PROFILE_KEY,)
    assert principal.administrative_override is False
    navigation = manager_navigation_principal(principal)
    assert navigation.access_key == GUEST_PROFILE_KEY
    assert navigation.administrative_override is False
    assert can_open_navigation_access(access_mode='restricted', allowed_profiles=('guest',), principal=navigation)
    assert not can_open_navigation_access(access_mode='restricted', allowed_profiles=('root',), principal=navigation)


def test_bootstrap_and_unavailable_backend_do_not_gain_guest_permissions():
    bootstrap = resolve_manager_principal(access=_access(bootstrap_root=True), user=None)
    assert bootstrap.profile_keys == ()
    fallback = public_navigation_principal()
    assert fallback.access_key is None
    assert not can_open_navigation_access(access_mode='restricted', allowed_profiles=('guest',), principal=fallback)
