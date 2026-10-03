from __future__ import annotations

from atlanticus.web.manager import ManagerPrincipal, ManagerPrincipalProvider
from atlanticus.web.navigation.api import (
    NavigationPrincipal,
    NavigationPrincipalProvider,
    NavigationUser,
)
from atlanticus.web.profiles.models import LOCAL_PROFILE_KEY
from atlanticus.web.users.local import LOCAL_USERS


def navigation_principal(
    principal: ManagerPrincipal,
    *,
    allow_local: bool = False,
) -> NavigationPrincipal:
    if not isinstance(principal, ManagerPrincipal):
        raise TypeError('Command Center navigation requires ManagerPrincipal')
    profile_key = principal.profile_keys[0] if len(principal.profile_keys) == 1 else None
    administrative_override = (profile_key == 'root' and not principal.is_local) or (
        profile_key == 'local' and principal.is_local and allow_local
    )
    local_user = next(
        (
            user
            for user in LOCAL_USERS
            if principal.is_local
            and profile_key == LOCAL_PROFILE_KEY
            and user.subject_id == principal.subject_id
        ),
        None,
    )
    background_color = (
        local_user.avatar_background_color
        if local_user is not None
        else principal.profile_background_color or '#3778C2'
    )
    text_color = (
        local_user.avatar_text_color
        if local_user is not None
        else principal.profile_text_color or '#FFFFFF'
    )
    return NavigationPrincipal(
        access_key=profile_key,
        administrative_override=administrative_override,
        user=NavigationUser(
            display_name=principal.display_name,
            profile_key=profile_key or 'public',
            profile_label=principal.profile_label
            or (profile_key.title() if profile_key is not None else 'Sin perfil'),
            profile_background_color=background_color,
            profile_text_color=text_color,
            avatar_text=principal.avatar_text
            or ''.join(word[0] for word in principal.display_name.split()[:2]).upper()
            or 'U',
            avatar_background_color=(
                local_user.avatar_background_color if local_user is not None else None
            ),
            avatar_text_color=local_user.avatar_text_color if local_user is not None else None,
        ),
    )


def create_navigation_principal_provider(
    principal_provider: ManagerPrincipalProvider,
    *,
    allow_local: bool = False,
) -> NavigationPrincipalProvider:
    if not callable(principal_provider):
        raise TypeError('Command Center principal provider must be callable')
    return NavigationPrincipalProvider(
        lambda: navigation_principal(principal_provider(), allow_local=allow_local)
    )
