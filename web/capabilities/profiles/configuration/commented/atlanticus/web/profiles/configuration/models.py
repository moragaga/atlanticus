from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from atlanticus.web.profiles.errors import ProfilesDefinitionError
from atlanticus.web.profiles.models import ProfileCatalog, ProfileDefinition


# ProfilesConfiguration persiste exclusivamente perfiles configurados por el usuario.
# Los system profiles se incorporan al construir el catálogo efectivo y no se serializan aquí.
@dataclass(frozen=True, slots=True)
class ProfilesConfiguration:
    profiles: tuple[ProfileDefinition, ...] = ()

    def __post_init__(self) -> None:
        # Construir el catálogo efectivo valida duplicados y evita redefinir
        # basic/root/guest/local.
        profiles = tuple(self.profiles)
        ProfileCatalog(profiles=profiles)
        object.__setattr__(self, 'profiles', profiles)

    def catalog(self) -> ProfileCatalog:
        # El consumer recibe system profiles más los configurados, sin duplicar datos durables.
        return ProfileCatalog(profiles=self.profiles)

    def to_document(self) -> dict[str, object]:
        # Sólo los perfiles configurables forman parte del documento Source.
        return {
            'profiles': [
                {
                    'key': profile.key,
                    'label': profile.label,
                    'background_color': profile.background_color,
                    'text_color': profile.text_color,
                }
                for profile in self.profiles
            ]
        }

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> ProfilesConfiguration:
        # La reconstrucción delega las invariantes del catálogo al mismo contrato
        # usado en runtime.
        try:
            raw_profiles = document['profiles']
            if not isinstance(raw_profiles, list) or not all(
                isinstance(item, dict) for item in raw_profiles
            ):
                raise TypeError
            return cls(
                profiles=tuple(
                    ProfileDefinition(
                        key=str(item['key']),
                        label=str(item['label']),
                        background_color=str(item['background_color']),
                        text_color=str(item['text_color']),
                    )
                    for item in raw_profiles
                )
            )
        except (KeyError, TypeError, ValueError, ProfilesDefinitionError) as error:
            raise ProfilesDefinitionError('Profiles configuration contract is invalid') from error
