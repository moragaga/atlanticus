from __future__ import annotations

from atlanticus.web.manager import ManagerPrincipal, ManagerPrincipalProvider
from atlanticus.web.navigation.api import (
    NavigationPrincipal,
    NavigationPrincipalProvider,
    NavigationUser,
)

_PROFILE_BACKGROUND_COLOR = '#3778C2'
_PROFILE_TEXT_COLOR = '#FFFFFF'


def navigation_principal(principal: ManagerPrincipal) -> NavigationPrincipal:
    if not isinstance(principal, ManagerPrincipal):
        raise TypeError('Command Center navigation requires ManagerPrincipal')
    profile_key = principal.profile_keys[0] if len(principal.profile_keys) == 1 else None
    initials = ''.join(word[0] for word in principal.display_name.split()[:2]).upper() or 'U'
    return NavigationPrincipal(
        access_key=profile_key,
        administrative_override=principal.administrative_override,
        user=NavigationUser(
            display_name=principal.display_name,
            profile_key=profile_key or 'public',
            profile_label=profile_key.title() if profile_key is not None else 'Sin perfil',
            profile_background_color=_PROFILE_BACKGROUND_COLOR,
            profile_text_color=_PROFILE_TEXT_COLOR,
            avatar_text=initials,
        ),
    )


def create_navigation_principal_provider(
    principal_provider: ManagerPrincipalProvider,
) -> NavigationPrincipalProvider:
    if not callable(principal_provider):
        raise TypeError('Command Center principal provider must be callable')
    return NavigationPrincipalProvider(lambda: navigation_principal(principal_provider()))
