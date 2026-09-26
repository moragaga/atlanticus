from __future__ import annotations

from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.navigation.api import NavigationPrincipal, NavigationUser


def public_navigation_principal() -> NavigationPrincipal:
    return NavigationPrincipal(
        access_key=None,
        user=NavigationUser(
            display_name='Visitante',
            profile_key='public',
            profile_label='Sin perfil',
            profile_background_color='#3778C2',
            profile_text_color='#FFFFFF',
            avatar_text='V',
        ),
    )


def manager_navigation_principal(
    principal: ManagerPrincipal, *, allow_local: bool = False
) -> NavigationPrincipal:
    profile_key = principal.profile_keys[0] if len(principal.profile_keys) == 1 else None
    administrative_override = (profile_key == 'root' and not principal.is_local) or (
        profile_key == 'local' and principal.is_local and allow_local
    )
    display_name = principal.display_name
    initials = ''.join(word[0] for word in display_name.split()[:2]).upper() or 'U'
    return NavigationPrincipal(
        access_key=profile_key,
        administrative_override=administrative_override,
        user=NavigationUser(
            display_name=display_name,
            profile_key=profile_key or 'public',
            profile_label=profile_key.title() if profile_key is not None else 'Sin perfil',
            profile_background_color='#3778C2',
            profile_text_color='#FFFFFF',
            avatar_text=initials,
        ),
    )
