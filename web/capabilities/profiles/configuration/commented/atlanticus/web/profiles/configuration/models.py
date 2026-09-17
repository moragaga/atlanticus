from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from atlanticus.web.profiles.errors import ProfilesDefinitionError
from atlanticus.web.profiles.models import ProfileCatalog, ProfileDefinition


# ProfilesConfiguration pertenece a la capa configuration, no al dominio core.
# Mantiene exactamente el contrato previo durante este corte de ownership.
@dataclass(frozen=True, slots=True)
class ProfilesConfiguration:
    profiles: tuple[ProfileDefinition, ...] = ()

    def __post_init__(self) -> None:
        # El catálogo aplica las invariantes de identidad y unicidad del dominio.
        profiles = tuple(self.profiles)
        ProfileCatalog(profiles=profiles)
        object.__setattr__(self, 'profiles', profiles)

    def catalog(self) -> ProfileCatalog:
        # Se reconstruye un catálogo inmutable a partir del estado configurado.
        return ProfileCatalog(profiles=self.profiles)

    def to_document(self) -> dict[str, object]:
        # El documento durable conserva el contrato existente sin migración implícita.
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
        # La reconstrucción valida forma documental y luego delega invariantes al dominio.
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
