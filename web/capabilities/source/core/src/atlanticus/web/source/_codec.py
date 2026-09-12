from __future__ import annotations

import base64
import hashlib
import json
from datetime import datetime, timezone

from atlanticus.web.source.errors import SourceInvalidCursorError
from atlanticus.web.source.models import (
    ConcurrencyToken,
    Digest,
    SourceKey,
    SourceManifest,
    SourceReleaseId,
    SourceReleaseMetadata,
    SourceReleaseRef,
    SourceReleaseSummary,
    SourceResourceMetadata,
)

SCHEMA_VERSION = 1
_DIGEST_ALGORITHM = 'sha256'


def encode_segment(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode('utf-8')).decode('ascii').rstrip('=')


def resource_metadata(logical_path: str, content: bytes) -> SourceResourceMetadata:
    return SourceResourceMetadata(
        logical_path=logical_path,
        byte_length=len(content),
        digest=_digest(content),
    )


def content_hash(resources: tuple[SourceResourceMetadata, ...]) -> Digest:
    document = [
        {
            'logical_path': item.logical_path,
            'byte_length': item.byte_length,
            'digest': _digest_to_document(item.digest),
        }
        for item in sorted(resources, key=lambda candidate: candidate.logical_path)
    ]
    return _digest(_json_bytes(document))


def token_for_manifest(payload: bytes) -> ConcurrencyToken:
    digest = hashlib.sha256(payload).digest()
    value = base64.urlsafe_b64encode(digest).decode('ascii').rstrip('=')
    return ConcurrencyToken(value)


def manifest_to_bytes(manifest: SourceManifest) -> bytes:
    return _json_bytes(
        {
            'schema_version': manifest.schema_version,
            'source_key': manifest.source_key.value,
            'current': _summary_to_document(manifest.current),
        }
    )


def manifest_from_bytes(payload: bytes) -> SourceManifest:
    document = json.loads(payload)
    if not isinstance(document, dict):
        raise TypeError('Manifest document must be an object')
    schema_version = _required_int(document, 'schema_version')
    if schema_version != SCHEMA_VERSION:
        raise ValueError('Unsupported source manifest schema version')
    return SourceManifest(
        schema_version=schema_version,
        source_key=SourceKey(_required_str(document, 'source_key')),
        current=_summary_from_document(_required_dict(document, 'current')),
    )


def release_metadata_to_bytes(metadata: SourceReleaseMetadata) -> bytes:
    return _json_bytes(
        {
            'schema_version': metadata.schema_version,
            'source_key': metadata.source_key.value,
            'release_ref': _release_ref_to_document(metadata.release_ref),
            'content_hash': _digest_to_document(metadata.content_hash),
            'resources': [_resource_metadata_to_document(item) for item in metadata.resources],
            'previous_published_release': (
                _release_ref_to_document(metadata.previous_published_release)
                if metadata.previous_published_release is not None
                else None
            ),
            'basis_release': (
                _release_ref_to_document(metadata.basis_release)
                if metadata.basis_release is not None
                else None
            ),
        }
    )


def release_metadata_from_bytes(payload: bytes) -> SourceReleaseMetadata:
    document = json.loads(payload)
    if not isinstance(document, dict):
        raise TypeError('Release metadata document must be an object')
    schema_version = _required_int(document, 'schema_version')
    if schema_version != SCHEMA_VERSION:
        raise ValueError('Unsupported source release schema version')
    resources = document.get('resources')
    if not isinstance(resources, list):
        raise TypeError('Release resources must be an array')
    if not all(isinstance(item, dict) for item in resources):
        raise TypeError('Release resource metadata must contain only objects')
    return SourceReleaseMetadata(
        schema_version=schema_version,
        source_key=SourceKey(_required_str(document, 'source_key')),
        release_ref=_release_ref_from_document(_required_dict(document, 'release_ref')),
        content_hash=_digest_from_document(_required_dict(document, 'content_hash')),
        resources=tuple(_resource_metadata_from_document(item) for item in resources),
        previous_published_release=_optional_release_ref(document, 'previous_published_release'),
        basis_release=_optional_release_ref(document, 'basis_release'),
    )


def encode_cursor(source_key: SourceKey, next_ref: SourceReleaseRef) -> str:
    payload = _json_bytes(
        {
            'version': 1,
            'source_key': source_key.value,
            'next_release': _release_ref_to_document(next_ref),
        }
    )
    return base64.urlsafe_b64encode(payload).decode('ascii').rstrip('=')


def decode_cursor(cursor: str, source_key: SourceKey) -> SourceReleaseRef:
    try:
        padding = '=' * (-len(cursor) % 4)
        payload = base64.urlsafe_b64decode((cursor + padding).encode('ascii'))
        document = json.loads(payload)
        if not isinstance(document, dict) or document.get('version') != 1:
            raise ValueError
        if document.get('source_key') != source_key.value:
            raise ValueError
        next_release = document.get('next_release')
        if not isinstance(next_release, dict):
            raise ValueError
        return _release_ref_from_document(next_release)
    except Exception as error:
        raise SourceInvalidCursorError('Source history cursor is invalid') from error


def _digest(payload: bytes) -> Digest:
    return Digest(_DIGEST_ALGORITHM, hashlib.sha256(payload).hexdigest())


def _summary_to_document(summary: SourceReleaseSummary) -> dict[str, object]:
    return {
        'release_id': summary.release_ref.release_id.value,
        'published_at_utc': _format_datetime(summary.release_ref.published_at_utc),
        'content_hash': _digest_to_document(summary.content_hash),
    }


def _summary_from_document(document: dict[str, object]) -> SourceReleaseSummary:
    return SourceReleaseSummary(
        release_ref=SourceReleaseRef(
            SourceReleaseId(_required_str(document, 'release_id')),
            _parse_datetime(_required_str(document, 'published_at_utc')),
        ),
        content_hash=_digest_from_document(_required_dict(document, 'content_hash')),
    )


def _release_ref_to_document(release_ref: SourceReleaseRef) -> dict[str, object]:
    return {
        'release_id': release_ref.release_id.value,
        'published_at_utc': _format_datetime(release_ref.published_at_utc),
    }


def _release_ref_from_document(document: dict[str, object]) -> SourceReleaseRef:
    return SourceReleaseRef(
        SourceReleaseId(_required_str(document, 'release_id')),
        _parse_datetime(_required_str(document, 'published_at_utc')),
    )


def _optional_release_ref(
    document: dict[str, object],
    key: str,
) -> SourceReleaseRef | None:
    value = document.get(key)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise TypeError(f'{key} must be an object or null')
    return _release_ref_from_document(value)


def _resource_metadata_to_document(metadata: SourceResourceMetadata) -> dict[str, object]:
    return {
        'logical_path': metadata.logical_path,
        'byte_length': metadata.byte_length,
        'digest': _digest_to_document(metadata.digest),
    }


def _resource_metadata_from_document(document: dict[str, object]) -> SourceResourceMetadata:
    return SourceResourceMetadata(
        logical_path=_required_str(document, 'logical_path'),
        byte_length=_required_int(document, 'byte_length'),
        digest=_digest_from_document(_required_dict(document, 'digest')),
    )


def _digest_to_document(digest: Digest) -> dict[str, str]:
    return {'algorithm': digest.algorithm, 'value': digest.value}


def _digest_from_document(document: dict[str, object]) -> Digest:
    return Digest(_required_str(document, 'algorithm'), _required_str(document, 'value'))


def _json_bytes(document: object) -> bytes:
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')


def _format_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')


def _parse_datetime(value: str) -> datetime:
    candidate = value[:-1] + '+00:00' if value.endswith('Z') else value
    parsed = datetime.fromisoformat(candidate)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('Stored source timestamp must be timezone-aware')
    return parsed.astimezone(timezone.utc)


def _required_str(document: dict[str, object], key: str) -> str:
    value = document[key]
    if not isinstance(value, str):
        raise TypeError(f'{key} must be a string')
    return value


def _required_int(document: dict[str, object], key: str) -> int:
    value = document[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f'{key} must be an integer')
    return value


def _required_dict(document: dict[str, object], key: str) -> dict[str, object]:
    value = document[key]
    if not isinstance(value, dict):
        raise TypeError(f'{key} must be an object')
    return value
