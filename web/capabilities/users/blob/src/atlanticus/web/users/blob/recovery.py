from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any, Protocol

from atlanticus.connectivity.storage import (
    StorageBlobNotFoundError,
    StorageConflictError,
    StorageError,
)
from atlanticus.connectivity.storage.models import StorageBlobProperties
from atlanticus.web.users.errors import UsersDefinitionError
from atlanticus.web.users.recovery import (
    ApprovedUsersSnapshot,
    UsersRecoveryAuditEvent,
    UsersRecoveryConflictError,
    UsersRecoveryUnavailableError,
    UsersReplaceBeforeImage,
)

_ID_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9-]{0,63}\Z')


class _StorageClient(Protocol):
    def download(self, *, container_name: str, blob_name: str) -> bytes: ...

    def upload(
        self,
        *,
        container_name: str,
        blob_name: str,
        data: bytes,
        overwrite: bool = True,
        metadata: Mapping[str, str] | None = None,
        content_type: str | None = None,
    ) -> None: ...

    def get_properties(
        self, *, container_name: str, blob_name: str
    ) -> StorageBlobProperties: ...

    def list_blobs(
        self, *, container_name: str, prefix: str | None = None, max_items: int | None = None
    ) -> tuple[StorageBlobProperties, ...]: ...


def _require_prefix(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip('/')
        or value != value.strip()
        or '\\' in value
        or any(segment in {'', '.', '..'} for segment in value.split('/'))
    ):
        raise UsersDefinitionError('Recovery blob prefix has an invalid format')
    return value


def _require_id(value: str) -> str:
    if not isinstance(value, str) or _ID_PATTERN.fullmatch(value) is None:
        raise UsersDefinitionError('Recovery artifact id has an invalid format')
    return value


def _write_new(
    client: _StorageClient,
    *,
    container_name: str,
    blob_name: str,
    document: dict[str, object],
) -> None:
    payload = json.dumps(
        document, sort_keys=True, ensure_ascii=False, separators=(',', ':'),
    ).encode('utf-8')
    try:
        client.upload(
            container_name=container_name,
            blob_name=blob_name,
            data=payload,
            overwrite=False,
            content_type='application/json',
        )
    except StorageConflictError as error:
        raise UsersRecoveryConflictError('Recovery artifact already exists') from error
    except StorageError as error:
        raise UsersRecoveryUnavailableError('Could not save recovery artifact') from error


class BlobApprovedUsersSnapshotStore:
    def __init__(self, *, client: _StorageClient, container_name: str, prefix: str) -> None:
        self._client = client
        self._container_name = _require_name(container_name)
        self._prefix = _require_prefix(prefix)

    def list_snapshot_ids(self, *, max_items: int = 200) -> tuple[str, ...]:
        return tuple(item[0] for item in self.list_snapshot_summaries(max_items=max_items))

    def list_snapshot_summaries(
        self, *, max_items: int = 200
    ) -> tuple[tuple[str, str | None], ...]:
        try:
            items = self._client.list_blobs(
                container_name=self._container_name,
                prefix=f'{self._prefix}/',
                max_items=max_items,
            )
        except StorageError as error:
            raise UsersRecoveryUnavailableError('Could not list Users snapshots') from error
        prefix = f'{self._prefix}/'
        candidates = (
            (
                item.name[len(prefix):-5],
                item.last_modified.isoformat() if item.last_modified else None,
                item.last_modified.timestamp() if item.last_modified else 0,
            )
            for item in items
            if item.name.startswith(prefix)
            and item.name.endswith('.json')
            and _ID_PATTERN.fullmatch(item.name[len(prefix):-5]) is not None
        )
        return tuple(
            (identifier, saved_at_utc)
            for identifier, saved_at_utc, _ in sorted(candidates, key=lambda x: x[2], reverse=True)
        )

    def save(self, snapshot: ApprovedUsersSnapshot) -> None:
        if not isinstance(snapshot, ApprovedUsersSnapshot):
            raise TypeError('snapshot must be ApprovedUsersSnapshot')
        _write_new(
            self._client,
            container_name=self._container_name,
            blob_name=f'{self._prefix}/{snapshot.snapshot_id}.json',
            document=snapshot.to_document(),
        )

    def load(self, snapshot_id: str) -> ApprovedUsersSnapshot:
        blob_name = f'{self._prefix}/{_require_id(snapshot_id)}.json'
        try:
            before = self._client.get_properties(
                container_name=self._container_name, blob_name=blob_name
            )
            raw = self._client.download(container_name=self._container_name, blob_name=blob_name)
            after = self._client.get_properties(
                container_name=self._container_name, blob_name=blob_name
            )
        except StorageBlobNotFoundError as error:
            raise UsersRecoveryUnavailableError('Approved snapshot is not available') from error
        except StorageError as error:
            raise UsersRecoveryUnavailableError('Could not read approved snapshot') from error
        if (
            not before.etag
            or not after.etag
            or before.etag != after.etag
        ):
            raise UsersRecoveryConflictError('Approved snapshot changed during read')
        try:
            document: Any = json.loads(raw.decode('utf-8'))
            snapshot = ApprovedUsersSnapshot.from_document(document)
        except (UnicodeDecodeError, json.JSONDecodeError, UsersDefinitionError) as error:
            raise UsersRecoveryConflictError('Approved snapshot is invalid') from error
        if snapshot.snapshot_id != snapshot_id:
            raise UsersRecoveryConflictError('Approved snapshot id does not match artifact')
        return snapshot


class BlobUsersReplaceBeforeImageStore:
    def __init__(self, *, client: _StorageClient, container_name: str, prefix: str) -> None:
        self._client = client
        self._container_name = _require_name(container_name)
        self._prefix = _require_prefix(prefix)

    def save(self, image: UsersReplaceBeforeImage) -> None:
        if not isinstance(image, UsersReplaceBeforeImage):
            raise TypeError('image must be UsersReplaceBeforeImage')
        _write_new(
            self._client,
            container_name=self._container_name,
            blob_name=f'{self._prefix}/{_require_id(image.operation_id)}.json',
            document=image.to_document(),
        )

    def load(self, operation_id: str) -> UsersReplaceBeforeImage:
        blob_name = f'{self._prefix}/{_require_id(operation_id)}.json'
        try:
            before = self._client.get_properties(
                container_name=self._container_name, blob_name=blob_name,
            )
            raw = self._client.download(container_name=self._container_name, blob_name=blob_name)
            after = self._client.get_properties(
                container_name=self._container_name, blob_name=blob_name,
            )
        except StorageBlobNotFoundError as error:
            raise UsersRecoveryUnavailableError(
                'Users replacement before-image is missing'
            ) from error
        except StorageError as error:
            raise UsersRecoveryUnavailableError(
                'Could not read Users replacement before-image'
            ) from error
        if not before.etag or before.etag != after.etag:
            raise UsersRecoveryConflictError('Users replacement before-image changed during read')
        try:
            image = UsersReplaceBeforeImage.from_document(json.loads(raw.decode('utf-8')))
        except (UnicodeDecodeError, json.JSONDecodeError, UsersDefinitionError) as error:
            raise UsersRecoveryConflictError(
                'Users replacement before-image is invalid'
            ) from error
        if image.operation_id != operation_id:
            raise UsersRecoveryConflictError('Users replacement before-image id does not match')
        return image


class BlobUsersRecoveryAuditStore:
    def __init__(self, *, client: _StorageClient, container_name: str, prefix: str) -> None:
        self._client = client
        self._container_name = _require_name(container_name)
        self._prefix = _require_prefix(prefix)

    def record(self, event: UsersRecoveryAuditEvent) -> None:
        if not isinstance(event, UsersRecoveryAuditEvent):
            raise TypeError('event must be UsersRecoveryAuditEvent')
        _require_id(event.operation_id)
        if event.stage not in {'started', 'completed', 'failed'}:
            raise UsersDefinitionError('Recovery audit stage is invalid')
        _write_new(
            self._client,
            container_name=self._container_name,
            blob_name=f'{self._prefix}/{event.operation_id}-{event.stage}.json',
            document=event.to_document(),
        )


def _require_name(value: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise UsersDefinitionError('Recovery container name has an invalid format')
    return value
