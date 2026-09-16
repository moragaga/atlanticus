from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from atlanticus.web.profiles.configuration import ProfilesConfiguration
from atlanticus.web.profiles.errors import ProfilesDefinitionError
from atlanticus.web.source.models import (
    ConcurrencyToken,
    HistoryPage,
    HistoryQuery,
    PublishRequest,
    PublishResult,
    SourceKey,
    SourceReleaseMetadata,
    SourceReleaseRef,
    SourceResource,
    SourceSnapshot,
)
from atlanticus.web.source.store import SourceStore
from atlanticus.web.users.configuration.canonical import (
    UsersConfiguration,
    UsersProfilesConfiguration,
)
from atlanticus.web.users.configuration.errors import (
    UsersConfigurationSourceError,
    UsersConfigurationValidationError,
)

USERS_SOURCE_DOCUMENT_TYPE = 'atlanticus_users_configuration_release'
USERS_SOURCE_SCHEMA_VERSION = 2
USERS_SOURCE_RESOURCE_PATH = 'users/configuration.json.gz'
PROFILES_SOURCE_DOCUMENT_TYPE = 'atlanticus_profiles_configuration_release'
PROFILES_SOURCE_SCHEMA_VERSION = 1
PROFILES_SOURCE_RESOURCE_PATH = 'profiles/configuration.json.gz'
DEFAULT_MAX_COMPRESSED_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_DECOMPRESSED_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class UsersSourcePayload:
    configuration: UsersConfiguration
    profiles: ProfilesConfiguration
    published_by: str

    def __post_init__(self) -> None:
        actor = self.published_by.strip()
        if not actor:
            raise UsersConfigurationSourceError('Users source publication actor must not be empty')
        UsersProfilesConfiguration(users=self.configuration, profiles=self.profiles)
        object.__setattr__(self, 'published_by', actor)

    def projection_payload(self) -> UsersProfilesConfiguration:
        return UsersProfilesConfiguration(users=self.configuration, profiles=self.profiles)


@dataclass(frozen=True, slots=True)
class UsersSourceRelease:
    metadata: SourceReleaseMetadata
    payload: UsersSourcePayload

    @property
    def release_ref(self) -> SourceReleaseRef:
        return self.metadata.release_ref

    @property
    def configuration(self) -> UsersConfiguration:
        return self.payload.configuration

    @property
    def profiles(self) -> ProfilesConfiguration:
        return self.payload.profiles

    @property
    def published_by(self) -> str:
        return self.payload.published_by


class UsersSourceCodec:
    def encode(
        self,
        *,
        configuration: UsersConfiguration,
        profiles: ProfilesConfiguration,
        published_by: str,
    ) -> tuple[SourceResource, ...]:
        payload = UsersSourcePayload(
            configuration=configuration,
            profiles=profiles,
            published_by=published_by,
        )
        users_document = {
            'document_type': USERS_SOURCE_DOCUMENT_TYPE,
            'schema_version': USERS_SOURCE_SCHEMA_VERSION,
            'published_by': payload.published_by,
            'configuration': payload.configuration.to_document(),
        }
        profiles_document = {
            'document_type': PROFILES_SOURCE_DOCUMENT_TYPE,
            'schema_version': PROFILES_SOURCE_SCHEMA_VERSION,
            'configuration': payload.profiles.to_document(),
        }
        return (
            SourceResource(
                logical_path=USERS_SOURCE_RESOURCE_PATH,
                content=_encode_document(users_document),
            ),
            SourceResource(
                logical_path=PROFILES_SOURCE_RESOURCE_PATH,
                content=_encode_document(profiles_document),
            ),
        )

    def decode(self, resources: tuple[SourceResource, ...]) -> UsersSourcePayload:
        users_resource = _require_single_resource(resources, USERS_SOURCE_RESOURCE_PATH)
        users_document = _decode_document(users_resource.content)
        if users_document.get('document_type') != USERS_SOURCE_DOCUMENT_TYPE:
            raise UsersConfigurationSourceError('Users source release document type is invalid')
        if users_document.get('schema_version') != USERS_SOURCE_SCHEMA_VERSION:
            raise UsersConfigurationSourceError('Users source release schema version is invalid')
        profiles_resource = _require_single_resource(resources, PROFILES_SOURCE_RESOURCE_PATH)
        profiles_document = _decode_document(profiles_resource.content)
        if profiles_document.get('document_type') != PROFILES_SOURCE_DOCUMENT_TYPE:
            raise UsersConfigurationSourceError('Profiles source release document type is invalid')
        if profiles_document.get('schema_version') != PROFILES_SOURCE_SCHEMA_VERSION:
            raise UsersConfigurationSourceError('Profiles source release schema version is invalid')
        try:
            users_configuration = users_document['configuration']
            profiles_configuration = profiles_document['configuration']
            if not isinstance(users_configuration, dict) or not isinstance(
                profiles_configuration, dict
            ):
                raise TypeError
            return UsersSourcePayload(
                configuration=UsersConfiguration.from_document(dict(users_configuration)),
                profiles=ProfilesConfiguration.from_document(dict(profiles_configuration)),
                published_by=str(users_document['published_by']),
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            ProfilesDefinitionError,
            UsersConfigurationValidationError,
        ) as error:
            raise UsersConfigurationSourceError(
                'Users/profiles source release contract is invalid'
            ) from error


class UsersSourceService:
    def __init__(
        self,
        *,
        source: SourceStore,
        source_key: SourceKey,
        codec: UsersSourceCodec | None = None,
    ) -> None:
        self._source = source
        self._source_key = source_key
        self._codec = codec or UsersSourceCodec()

    @property
    def source_key(self) -> SourceKey:
        return self._source_key

    def get_current(self) -> SourceSnapshot:
        return self._source.get_current(self._source_key)

    def load_current(self) -> UsersSourceRelease | None:
        snapshot = self.get_current()
        if snapshot.current is None:
            return None
        return self.load_release(snapshot.current.release_ref)

    def load_release(self, release_ref: SourceReleaseRef) -> UsersSourceRelease:
        metadata, resources = self._source.read_release(self._source_key, release_ref)
        if metadata.source_key != self._source_key:
            raise UsersConfigurationSourceError(
                'Users source store returned a different source key'
            )
        if metadata.release_ref != release_ref:
            raise UsersConfigurationSourceError(
                'Users source store returned a different source release'
            )
        return UsersSourceRelease(
            metadata=metadata,
            payload=self._codec.decode(resources),
        )

    def publish_configuration(
        self,
        configuration: UsersConfiguration,
        profiles: ProfilesConfiguration,
        *,
        published_by: str,
        expected_concurrency_token: ConcurrencyToken | None,
        basis_release: SourceReleaseRef | None,
    ) -> PublishResult:
        resources = self._codec.encode(
            configuration=configuration,
            profiles=profiles,
            published_by=published_by,
        )
        return self._source.publish(
            PublishRequest(
                source_key=self._source_key,
                resources=resources,
                expected_concurrency_token=expected_concurrency_token,
                basis_release=basis_release,
            )
        )

    def query_history(
        self,
        *,
        page_size: int = 20,
        cursor: str | None = None,
    ) -> HistoryPage:
        return self._source.query_history(
            HistoryQuery(
                source_key=self._source_key,
                page_size=page_size,
                cursor=cursor,
            )
        )


def _require_single_resource(
    resources: tuple[SourceResource, ...],
    logical_path: str,
) -> SourceResource:
    matches = tuple(resource for resource in resources if resource.logical_path == logical_path)
    if len(matches) != 1:
        raise UsersConfigurationSourceError(
            f'Users source release must contain exactly one {logical_path} resource'
        )
    return matches[0]


def _encode_document(document: dict[str, object]) -> bytes:
    raw = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return gzip.compress(raw, mtime=0)


def _decode_document(payload: bytes) -> dict[str, Any]:
    if len(payload) > DEFAULT_MAX_COMPRESSED_BYTES:
        raise UsersConfigurationSourceError('Users source release compressed payload is too large')
    try:
        with gzip.GzipFile(fileobj=BytesIO(payload), mode='rb') as stream:
            raw = stream.read(DEFAULT_MAX_DECOMPRESSED_BYTES + 1)
    except OSError as error:
        raise UsersConfigurationSourceError(
            'Users source release payload is not valid gzip data'
        ) from error
    if len(raw) > DEFAULT_MAX_DECOMPRESSED_BYTES:
        raise UsersConfigurationSourceError(
            'Users source release decompressed payload is too large'
        )
    try:
        document = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UsersConfigurationSourceError(
            'Users source release payload is not valid JSON'
        ) from error
    if not isinstance(document, dict):
        raise UsersConfigurationSourceError('Users source release payload root must be an object')
    return document
