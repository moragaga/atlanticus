from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ada.web.access.errors import AdaAccessDefinitionError
from ada.web.access.models import (
    EffectiveAdaAccess,
    ProfileAccessGrant,
    UserProfileAssignment,
    validate_profile_references,
)
from atlanticus.web.profiles.models import ProfileCatalog


@dataclass(frozen=True, slots=True)
class AdaAccessConfiguration:
    user_profiles: tuple[UserProfileAssignment, ...] = ()
    profile_access: tuple[ProfileAccessGrant, ...] = ()

    def __post_init__(self) -> None:
        user_profiles = tuple(self.user_profiles)
        profile_access = tuple(self.profile_access)
        user_ids = tuple(assignment.user_id for assignment in user_profiles)
        profile_keys = tuple(grant.profile_key for grant in profile_access)
        if len(user_ids) != len(set(user_ids)):
            raise AdaAccessDefinitionError('ADA access user assignments must be unique')
        if len(profile_keys) != len(set(profile_keys)):
            raise AdaAccessDefinitionError('ADA access profile grants must be unique')
        object.__setattr__(
            self,
            'user_profiles',
            tuple(sorted(user_profiles, key=lambda assignment: assignment.user_id)),
        )
        object.__setattr__(
            self,
            'profile_access',
            tuple(sorted(profile_access, key=lambda grant: grant.profile_key)),
        )

    def validate_profiles(self, profiles: ProfileCatalog) -> None:
        for assignment in self.user_profiles:
            validate_profile_references(profile_keys=assignment.profile_keys, profiles=profiles)
        validate_profile_references(
            profile_keys=tuple(grant.profile_key for grant in self.profile_access),
            profiles=profiles,
        )

    def resolve(self, user_id: str, *, profiles: ProfileCatalog) -> EffectiveAdaAccess:
        normalized_user_id = user_id.strip()
        assignment = next(
            (item for item in self.user_profiles if item.user_id == normalized_user_id),
            None,
        )
        if assignment is None:
            return EffectiveAdaAccess(user_id=normalized_user_id)
        validate_profile_references(profile_keys=assignment.profile_keys, profiles=profiles)
        grants = {grant.profile_key: grant for grant in self.profile_access}
        access_keys: list[str] = []
        seen_access_keys: set[str] = set()
        for profile_key in assignment.profile_keys:
            grant = grants.get(profile_key)
            if grant is None:
                continue
            profiles.require(grant.profile_key)
            for access_key in grant.access_keys:
                if access_key not in seen_access_keys:
                    seen_access_keys.add(access_key)
                    access_keys.append(access_key)
        return EffectiveAdaAccess(
            user_id=assignment.user_id,
            profile_keys=assignment.profile_keys,
            access_keys=tuple(access_keys),
        )

    def to_document(self) -> dict[str, object]:
        return {
            'user_profiles': [
                {
                    'user_id': assignment.user_id,
                    'profile_keys': list(assignment.profile_keys),
                }
                for assignment in self.user_profiles
            ],
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
            raw_user_profiles = document['user_profiles']
            raw_profile_access = document['profile_access']
            if not isinstance(raw_user_profiles, list) or not all(
                isinstance(item, dict) for item in raw_user_profiles
            ):
                raise TypeError
            if not isinstance(raw_profile_access, list) or not all(
                isinstance(item, dict) for item in raw_profile_access
            ):
                raise TypeError
            return cls(
                user_profiles=tuple(
                    UserProfileAssignment(
                        user_id=_text(item, 'user_id'),
                        profile_keys=_text_tuple(item, 'profile_keys'),
                    )
                    for item in raw_user_profiles
                ),
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
