from __future__ import annotations

from datetime import datetime
from typing import Any

from atlanticus.web.profiles.configuration.errors import ProfilesConfigurationProjectionError
from atlanticus.web.profiles.errors import ProfilesDefinitionError
from atlanticus.web.profiles.models import (
    SYSTEM_PROFILE_KEYS,
    ProfileCatalog,
    ProfileDefinition,
)
from atlanticus.web.projection.models import ProjectionRecord
from atlanticus.web.source.models import SourceKey, SourceReleaseId

PROFILES_PROJECTION_DOCUMENT_TYPE = 'atlanticus_profiles_projection_record'
PROFILES_PROJECTION_SCHEMA_VERSION = 1


def profiles_projection_to_document(
    projection: ProjectionRecord[ProfileCatalog],
    *,
    item_id: str | None = None,
    partition_key: str | None = None,
) -> dict[str, object]:
    if not isinstance(projection.payload, ProfileCatalog):
        raise ProfilesConfigurationProjectionError(
            'Profiles projection payload must be a ProfileCatalog'
        )
    document: dict[str, object] = {
        'document_type': PROFILES_PROJECTION_DOCUMENT_TYPE,
        'schema_version': PROFILES_PROJECTION_SCHEMA_VERSION,
        'source_key': projection.source_key.value,
        'source_release_id': projection.source_release_id.value,
        'source_published_at_utc': projection.source_published_at_utc.isoformat(),
        'projected_at_utc': projection.projected_at_utc.isoformat(),
        'payload': {
            'profiles': [
                _profile_to_document(profile)
                for profile in projection.payload.all()
                if profile.key not in SYSTEM_PROFILE_KEYS
            ]
        },
    }
    if item_id is not None:
        document['id'] = item_id
    if partition_key is not None:
        document['partition_key'] = partition_key
    return document


def profiles_projection_from_document(
    document: dict[str, Any],
) -> ProjectionRecord[ProfileCatalog]:
    if document.get('document_type') != PROFILES_PROJECTION_DOCUMENT_TYPE:
        raise ProfilesConfigurationProjectionError(
            'Profiles projection document type is invalid'
        )
    if document.get('schema_version') != PROFILES_PROJECTION_SCHEMA_VERSION:
        raise ProfilesConfigurationProjectionError(
            'Profiles projection schema version is invalid'
        )
    try:
        payload = document['payload']
        if not isinstance(payload, dict):
            raise TypeError
        raw_profiles = payload['profiles']
        if not isinstance(raw_profiles, list) or not all(
            isinstance(item, dict) for item in raw_profiles
        ):
            raise TypeError
        catalog = ProfileCatalog(
            profiles=tuple(_profile_from_document(item) for item in raw_profiles)
        )
        return ProjectionRecord(
            source_key=SourceKey(str(document['source_key'])),
            source_release_id=SourceReleaseId(str(document['source_release_id'])),
            source_published_at_utc=datetime.fromisoformat(
                str(document['source_published_at_utc'])
            ),
            projected_at_utc=datetime.fromisoformat(str(document['projected_at_utc'])),
            payload=catalog,
        )
    except (KeyError, TypeError, ValueError, ProfilesDefinitionError) as error:
        raise ProfilesConfigurationProjectionError(
            'Profiles projection contract is invalid'
        ) from error


def _profile_to_document(profile: ProfileDefinition) -> dict[str, object]:
    return {
        'key': profile.key,
        'label': profile.label,
        'background_color': profile.background_color,
        'text_color': profile.text_color,
    }


def _profile_from_document(document: dict[str, Any]) -> ProfileDefinition:
    return ProfileDefinition(
        key=str(document['key']),
        label=str(document['label']),
        background_color=str(document['background_color']),
        text_color=str(document['text_color']),
    )
