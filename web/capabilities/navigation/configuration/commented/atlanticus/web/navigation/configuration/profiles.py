# Navigation define sólo la forma mínima que necesita para ofrecer restricciones por perfil.
# La composición decide si existe un catálogo externo y cómo convertirlo a estas opciones.
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from atlanticus.web.navigation.configuration.errors import NavigationConfigurationValidationError


@dataclass(frozen=True, slots=True)
class NavigationProfileOption:
    key: str
    label: str

    def __post_init__(self) -> None:
        # La key es el contrato durable que Navigation persiste en allowed_profiles.
        key = self.key.strip().casefold()
        label = self.label.strip()
        if not key:
            raise NavigationConfigurationValidationError(
                'Navigation profile option key must not be empty'
            )
        if any(character.isspace() for character in key):
            raise NavigationConfigurationValidationError(
                'Navigation profile option key must not contain spaces'
            )
        if not label:
            raise NavigationConfigurationValidationError(
                'Navigation profile option label must not be empty'
            )
        object.__setattr__(self, 'key', key)
        object.__setattr__(self, 'label', label)


# El provider es opcional: Navigation debe poder operar sin una capability Profiles compuesta.
NavigationProfileOptionsProvider = Callable[[], tuple[NavigationProfileOption, ...]]


def profile_options(
    provider: NavigationProfileOptionsProvider | None = None,
) -> tuple[NavigationProfileOption, ...]:
    if provider is None:
        return ()
    options = tuple(provider())
    keys = [option.key for option in options]
    if len(keys) != len(set(keys)):
        raise NavigationConfigurationValidationError(
            'Navigation profile option keys must be unique'
        )
    return options
