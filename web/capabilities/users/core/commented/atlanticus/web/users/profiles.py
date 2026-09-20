from __future__ import annotations

from collections.abc import Callable

from atlanticus.web.profiles.errors import ProfilesDefinitionError
from atlanticus.web.profiles.models import (
    GUEST_PROFILE_KEY,
    LOCAL_PROFILE_KEY,
    ROOT_PROFILE_KEY,
    ProfileCatalog,
    ProfileDefinition,
    normalize_profile_key,
)
from atlanticus.web.users.errors import UsersDefinitionError

# Users consume el catálogo efectivo de Profiles mediante un provider de composición.
UsersProfileCatalogProvider = Callable[[], ProfileCatalog]


def normalize_managed_profile_key(value: str) -> str:
    try:
        normalized = normalize_profile_key(value)
    except ProfilesDefinitionError as error:
        raise UsersDefinitionError('Managed user profile key is invalid') from error
    # local pertenece exclusivamente al runtime local Jane/John.
    if normalized == LOCAL_PROFILE_KEY:
        raise UsersDefinitionError('Managed user profile must not be local')
    return normalized


def resolve_profile_catalog(provider: UsersProfileCatalogProvider) -> ProfileCatalog:
    catalog = provider()
    if not isinstance(catalog, ProfileCatalog):
        raise UsersDefinitionError('Users profile catalog provider returned an invalid catalog')
    return catalog


def require_managed_profile(
    profile_key: str,
    *,
    profiles: ProfileCatalog,
) -> ProfileDefinition:
    normalized = normalize_managed_profile_key(profile_key)
    # guest puede existir como estado transitorio, pero no puede seleccionarse como perfil administrativo.
    if normalized == GUEST_PROFILE_KEY:
        raise UsersDefinitionError('Managed user profile must not be guest')
    try:
        return profiles.require(normalized)
    except ProfilesDefinitionError as error:
        raise UsersDefinitionError(f'Unknown managed user profile {normalized!r}') from error


def available_managed_profiles(profiles: ProfileCatalog) -> tuple[ProfileDefinition, ...]:
    # La administración solo expone perfiles persistibles: excluye los perfiles runtime local y guest transitorio.
    excluded = {LOCAL_PROFILE_KEY, GUEST_PROFILE_KEY}
    return tuple(profile for profile in profiles.all() if profile.key not in excluded)


def has_full_access_profile(profile_key: str) -> bool:
    try:
        normalized = normalize_profile_key(profile_key)
    except ProfilesDefinitionError as error:
        raise UsersDefinitionError('User profile key is invalid') from error
    # La semántica root/local se deriva de las keys propiedad de Profiles.
    return normalized in {ROOT_PROFILE_KEY, LOCAL_PROFILE_KEY}
