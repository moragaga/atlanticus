from __future__ import annotations

from threading import RLock

from atlanticus.web.users.activity.contracts import StoredUserActivity
from atlanticus.web.users.activity.errors import UserActivityConflictError
from atlanticus.web.users.activity.models import UserActivityDocument


class MemoryUserActivityRepository:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], StoredUserActivity] = {}
        self._lock = RLock()

    def load(self, *, document_id: str, partition_key: str) -> StoredUserActivity | None:
        with self._lock:
            return self._items.get((partition_key, document_id))

    def save(
        self,
        document: UserActivityDocument,
        *,
        expected_revision: str | None,
    ) -> StoredUserActivity:
        key = (document.partition_key, document.id)
        with self._lock:
            current = self._items.get(key)
            current_revision = current.revision if current is not None else None
            if current_revision != expected_revision:
                raise UserActivityConflictError('User activity revision conflict')
            revision = str(int(current_revision or '0') + 1)
            stored = StoredUserActivity(document=document, revision=revision)
            self._items[key] = stored
            return stored

    def documents(self) -> tuple[UserActivityDocument, ...]:
        with self._lock:
            return tuple(item.document for item in self._items.values())
