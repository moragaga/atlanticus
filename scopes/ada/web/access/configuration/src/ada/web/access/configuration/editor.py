from __future__ import annotations

from dataclasses import replace

from ada.web.access.configuration.models import (
    UNRESTRICTED_ACCESS_PROFILE_KEYS,
    AdaAccessConfiguration,
)
from ada.web.access.errors import AdaAccessDefinitionError
from ada.web.access.models import ProfileAccessGrant, normalize_access_key
from atlanticus.web.profiles.models import normalize_profile_key


def build_initial_configuration() -> AdaAccessConfiguration:
    return AdaAccessConfiguration()


def create_access_key(
    configuration: AdaAccessConfiguration,
    *,
    access_key: str,
) -> AdaAccessConfiguration:
    normalized = normalize_access_key(access_key)
    if normalized in configuration.access_keys:
        raise AdaAccessDefinitionError(f'ADA access key {normalized!r} already exists')
    return replace(configuration, access_keys=(*configuration.access_keys, normalized))


def remove_access_key(
    configuration: AdaAccessConfiguration,
    *,
    access_key: str,
) -> AdaAccessConfiguration:
    normalized = normalize_access_key(access_key)
    if normalized not in configuration.access_keys:
        raise AdaAccessDefinitionError(f'ADA access key {normalized!r} does not exist')
    for grant in configuration.profile_access:
        if normalized in grant.access_keys:
            raise AdaAccessDefinitionError(
                f'ADA access key {normalized!r} is still assigned to profile {grant.profile_key!r}'
            )
    return replace(
        configuration,
        access_keys=tuple(key for key in configuration.access_keys if key != normalized),
    )


def set_profile_access(
    configuration: AdaAccessConfiguration,
    *,
    profile_key: str,
    access_keys: tuple[str, ...],
) -> AdaAccessConfiguration:
    normalized_profile_key = normalize_profile_key(profile_key)
    if normalized_profile_key in UNRESTRICTED_ACCESS_PROFILE_KEYS:
        raise AdaAccessDefinitionError(
            f'ADA unrestricted profile {normalized_profile_key!r} '
            'does not accept explicit access grants'
        )
    grant = ProfileAccessGrant(
        profile_key=normalized_profile_key,
        access_keys=access_keys,
    )
    unknown = tuple(key for key in grant.access_keys if key not in configuration.access_keys)
    if unknown:
        raise AdaAccessDefinitionError(
            f'ADA access profile grant references undefined access key {unknown[0]!r}'
        )

    grants = [
        existing
        for existing in configuration.profile_access
        if existing.profile_key != normalized_profile_key
    ]
    if grant.access_keys:
        grants.append(grant)
    return replace(configuration, profile_access=tuple(grants))
