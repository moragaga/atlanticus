from __future__ import annotations

# Espejo pedagógico del módulo productivo equivalente.
# Navigation separa autorización funcional (public/restricted) de recovery administrativo.
# Los perfiles root/local nunca son grants explícitos; llegan como administrative_override confiable.


from atlanticus.web.navigation.models import (
    NavigationAccessMode,
    NavigationPrincipal,
)


def can_open_navigation_access(
    *,
    access_mode: NavigationAccessMode,
    allowed_profiles: tuple[str, ...],
    principal: NavigationPrincipal,
) -> bool:
    if principal.administrative_override or principal.unrestricted:
        return True
    if access_mode == 'public':
        return True
    return principal.access_key in allowed_profiles
