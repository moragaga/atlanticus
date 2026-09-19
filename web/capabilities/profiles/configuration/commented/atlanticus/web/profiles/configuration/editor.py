from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from atlanticus.web.profiles.configuration.models import ProfilesConfiguration
from atlanticus.web.profiles.errors import ProfilesDefinitionError
from atlanticus.web.profiles.models import ProfileDefinition, normalize_profile_key


# El editor comienza siempre desde una configuración durable vacía; los perfiles del sistema
# pertenecen al catálogo efectivo de Profiles core y no se copian al documento configurable.
def build_initial_configuration() -> ProfilesConfiguration:
    return ProfilesConfiguration()


# La identidad técnica de un perfil nuevo es un UUID4 opaco. El nombre visible nunca participa
# en la key, por lo que espacios, tildes, idioma o cambios posteriores de label no rompen referencias.
def create_profile(
    configuration: ProfilesConfiguration,
    *,
    label: str,
    background_color: str,
    text_color: str = '#FFFFFF',
) -> ProfilesConfiguration:
    profile = ProfileDefinition(
        key=str(uuid4()),
        label=label,
        background_color=background_color,
        text_color=text_color,
    )
    # Los perfiles configurados conservan su orden de creación.
    return replace(configuration, profiles=(*configuration.profiles, profile))


# La edición recibe la key interna del registro seleccionado pero nunca la recalcula.
# Sólo cambia representación visible; así Navigation y ADA Access conservan referencias estables.
def update_profile(
    configuration: ProfilesConfiguration,
    *,
    key: str,
    label: str,
    background_color: str,
    text_color: str,
) -> ProfilesConfiguration:
    normalized_key = normalize_profile_key(key)
    found = False
    profiles: list[ProfileDefinition] = []
    for profile in configuration.profiles:
        if profile.key != normalized_key:
            profiles.append(profile)
            continue
        found = True
        profiles.append(
            ProfileDefinition(
                key=profile.key,
                label=label,
                background_color=background_color,
                text_color=text_color,
            )
        )
    # Los perfiles del sistema no están en ProfilesConfiguration, por lo que tampoco son editables aquí.
    if not found:
        raise ProfilesDefinitionError(f'Configured profile {normalized_key!r} does not exist')
    return replace(configuration, profiles=tuple(profiles))
