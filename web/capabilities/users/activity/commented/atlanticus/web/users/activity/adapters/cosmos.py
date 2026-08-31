# Adapter Cosmos sin clientes globales, secretos ni configuración propia.
# Recibe el container ya compuesto y conserva optimistic concurrency mediante ETag.
from __future__ import annotations

from typing import Any, Protocol

from atlanticus.web.users.activity.contracts import StoredUserActivity
from atlanticus.web.users.activity.errors import UserActivityConflictError, UserActivityError
from atlanticus.web.users.activity.models import UserActivityDocument


class CosmosContainer(Protocol):
    def read_item(self, *, item: str, partition_key: str) -> dict[str, Any]: ...

    def create_item(self, *, body: dict[str, object]) -> dict[str, Any]: ...

    def replace_item(
        self,
        *,
        item: str,
        body: dict[str, object],
        etag: str,
        match_condition: str,
    ) -> dict[str, Any]: ...


class CosmosUserActivityRepository:
    def __init__(self, container: CosmosContainer) -> None:
        self._container = container

    def load(self, *, document_id: str, partition_key: str) -> StoredUserActivity | None:
        try:
            payload = self._container.read_item(item=document_id, partition_key=partition_key)
        except Exception as error:
            if _status_code(error) == 404:
                return None
            raise UserActivityError('User activity Cosmos read failed') from error
        return _stored(payload)

    def save(
        self,
        document: UserActivityDocument,
        *,
        expected_revision: str | None,
    ) -> StoredUserActivity:
        body = document.to_document()
        try:
            if expected_revision is None:
                payload = self._container.create_item(body=body)
            else:
                payload = self._container.replace_item(
                    item=document.id,
                    body=body,
                    etag=expected_revision,
                    match_condition='IfNotModified',
                )
        except Exception as error:
            if _status_code(error) in {409, 412}:
                raise UserActivityConflictError('User activity Cosmos revision conflict') from error
            raise UserActivityError('User activity Cosmos write failed') from error
        return _stored(payload)


def _stored(payload: dict[str, Any]) -> StoredUserActivity:
    revision = str(payload.get('_etag') or '').strip()
    if not revision:
        raise UserActivityError('User activity Cosmos document does not contain an ETag')
    return StoredUserActivity(
        document=UserActivityDocument.from_document(payload),
        revision=revision,
    )


def _status_code(error: Exception) -> int | None:
    value = getattr(error, 'status_code', None)
    return value if isinstance(value, int) else None
