from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ada.web.access.errors import AdaAccessDefinitionError
from ada.web.access.models import (
    EffectiveAdaAccess,
    ProfileAccessGrant,
    validate_profile_references,
)
from atlanticus.web.profiles.models import ProfileCatalog, normalize_profile_key


@dataclass(frozen=True, slots=True)
class AdaAccessConfiguration:
    profile_access: tuple[ProfileAccessGrant, ...] = ()

    def __post_init__(self) -> None:
        profile_access = tuple(self.profile_access)
        profile_keys = tuple(grant.profile_key for grant in profile_access)
        if len(profile_keys) != len(set(profile_keys)):
            raise AdaAccessDefinitionError('ADA access profile grants must be unique')
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
            if 'user_profiles' in document:
                raise TypeError
            raw_profile_access = document['profile_access']
            if not isinstance(raw_profile_access, list) or not all(
                isinstance(item, dict) for item in raw_profile_access
            ):
                raise TypeError
            return cls(
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
