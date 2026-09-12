from __future__ import annotations

from types import SimpleNamespace

import pytest

from atlanticus.connectivity.storage import (
    StorageClient,
    StorageConflictError,
    StorageConnectionStringCredential,
    StorageSettings,
)
from atlanticus.connectivity.storage.client import _StorageSdk


class FakeHttpError(Exception):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__('private-url?sig=secret')


class FakeRequestError(Exception):
    pass


class FakeResponseError(Exception):
    pass


class FakeContentSettings:
    def __init__(self, *, content_type: str) -> None:
        self.content_type = content_type


class FakeMatchConditions:
    IfNotModified = object()


class FakeBlob:
    def __init__(self) -> None:
        self.uploads: list[tuple[object, dict[str, object]]] = []
        self.error: BaseException | None = None

    def upload_blob(self, data: object, **kwargs: object) -> None:
        if self.error is not None:
            raise self.error
        self.uploads.append((data, kwargs))


class FakeService:
    def __init__(self, blob: FakeBlob) -> None:
        self.blob = blob

    def get_blob_client(self, *, container: str, blob: str) -> FakeBlob:
        assert container == 'data'
        assert blob == 'manifest.json'
        return self.blob


def _client(blob: FakeBlob) -> StorageClient:
    client = StorageClient(
        settings=StorageSettings(
            credential=StorageConnectionStringCredential(
                connection_string='DefaultEndpointsProtocol=https;AccountKey=private-secret'
            )
        )
    )
    client._client = FakeService(blob)
    client._sdk = _StorageSdk(
        BlobServiceClient=SimpleNamespace,
        ContentSettings=FakeContentSettings,
        HttpResponseError=FakeHttpError,
        ServiceRequestError=FakeRequestError,
        ServiceResponseError=FakeResponseError,
        MatchConditions=FakeMatchConditions,
    )
    return client


def test_upload_if_match_uses_observed_etag_and_if_not_modified() -> None:
    blob = FakeBlob()
    client = _client(blob)

    client.upload_if_match(
        container_name='data',
        blob_name='manifest.json',
        data=b'candidate',
        etag='"observed-etag"',
        metadata={'kind': 'manifest'},
        content_type='application/json',
    )

    assert len(blob.uploads) == 1
    data, kwargs = blob.uploads[0]
    assert data == b'candidate'
    content_settings = kwargs.pop('content_settings')
    assert isinstance(content_settings, FakeContentSettings)
    assert content_settings.content_type == 'application/json'
    assert kwargs == {
        'overwrite': True,
        'metadata': {'kind': 'manifest'},
        'etag': '"observed-etag"',
        'match_condition': FakeMatchConditions.IfNotModified,
    }


def test_upload_if_match_maps_precondition_failure_to_storage_conflict() -> None:
    blob = FakeBlob()
    blob.error = FakeHttpError(412)
    client = _client(blob)

    with pytest.raises(StorageConflictError) as captured:
        client.upload_if_match(
            container_name='data',
            blob_name='manifest.json',
            data=b'candidate',
            etag='"stale-etag"',
        )

    assert captured.value.__cause__ is None
    assert 'private' not in repr(captured.value)


def test_upload_if_match_rejects_invalid_etag_before_upload() -> None:
    blob = FakeBlob()
    client = _client(blob)

    with pytest.raises(TypeError, match='etag must be non-empty text'):
        client.upload_if_match(
            container_name='data',
            blob_name='manifest.json',
            data=b'candidate',
            etag=' ',
        )

    assert blob.uploads == []
