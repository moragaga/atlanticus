from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable


@runtime_checkable
class TimeStatusStoreDocumentSource(Protocol):
    def load_time_status_document(self, *, tool_key: str) -> Mapping[str, object] | None: ...
