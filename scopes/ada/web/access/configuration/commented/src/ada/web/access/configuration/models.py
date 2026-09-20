# AdaAccessConfiguration mantiene dos hechos: qué accesos existen y qué accesos tiene cada Profile.
# La access_key es la identidad estable; no existe un segundo id ni una entidad paralela.
# Los grants sólo pueden referenciar claves declaradas en el mismo documento.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ada.web.access.errors import AdaAccessDefinitionError
from ada.web.access.models import (
    EffectiveAdaAccess,
    ProfileAccessGrant,
    normalize_access_key,
    validate_profile_references,
)
from atlanticus.web.profiles.models import ProfileCatalog, normalize_profile_key


@dataclass(frozen=True, slots=True)
class AdaAccessConfiguration:
    access_keys: tuple[str, ...] = ()
    profile_access: tuple[ProfileAccessGrant, ...] = ()

    def __post_init__(self) -> None:
        access_keys = tuple(normalize_access_key(value) for value in self.access_keys)
        if len(access_keys) != len(set(access_keys)):
            raise AdaAccessDefinitionError('ADA access definitions must be unique')
        access_keys = tuple(sorted(access_keys))

        profile_access = tuple(self.profile_access)
        profile_keys = tuple(grant.profile_key for grant in profile_access)
        if len(profile_keys) != len(set(profile_keys)):
            raise AdaAccessDefinitionError('ADA access profile grants must be unique')

        defined = set(access_keys)
        for grant in profile_access:
            unknown = tuple(key for key in grant.access_keys if key not in defined)
            if unknown:
                raise AdaAccessDefinitionError(
                    f'ADA access profile grant references undefined access key {unknown[0]!r}'
                )

        object.__setattr__(self, 'access_keys', access_keys)
        object.__setattr__(
            self,
            'profile_access',
            tuple(sorted(profile_access, key=lambda grant: grant.profile_key)),
        )

    def validate_profiles(self, profiles: ProfileCatalog) -> None:
        validate_profile_references(
            profile_keys=tuple(grant.profile_key for grant in self.profile_access),
            profiles=profiles,
        )

    def resolve(
        self,
        profile_key: str,
        *,
        profiles: ProfileCatalog,
    ) -> EffectiveAdaAccess:
        normalized_profile_key = normalize_profile_key(profile_key)
        profiles.require(normalized_profile_key)
        grant = next(
            (item for item in self.profile_access if item.profile_key == normalized_profile_key),
            None,
        )
        return EffectiveAdaAccess(
            profile_key=normalized_profile_key,
            access_keys=() if grant is None else grant.access_keys,
        )

    def to_document(self) -> dict[str, object]:
        return {
            'access_keys': list(self.access_keys),
            'profile_access': [
                {
                    'profile_key': grant.profile_key,
                    'access_keys': list(grant.access_keys),
                }
                for grant in self.profile_access
            ],
        }

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> AdaAccessConfiguration:
        try:
            raw_access_keys = document['access_keys']
            raw_profile_access = document['profile_access']
            if not isinstance(raw_access_keys, list) or not all(
                isinstance(item, str) for item in raw_access_keys
            ):
                raise TypeError
            if not isinstance(raw_profile_access, list) or not all(
                isinstance(item, dict) for item in raw_profile_access
            ):
                raise TypeError
            return cls(
                access_keys=tuple(raw_access_keys),
                profile_access=tuple(
                    ProfileAccessGrant(
                        profile_key=_text(item, 'profile_key'),
                        access_keys=_text_tuple(item, 'access_keys'),
                    )
                    for item in raw_profile_access
                ),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise AdaAccessDefinitionError(
                'ADA access configuration contract is invalid'
            ) from error


def _text(document: dict[str, Any], key: str) -> str:
    value = document[key]
    if not isinstance(value, str):
        raise TypeError
    return value


def _text_tuple(document: dict[str, Any], key: str) -> tuple[str, ...]:
    value = document[key]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError
    return tuple(value)
