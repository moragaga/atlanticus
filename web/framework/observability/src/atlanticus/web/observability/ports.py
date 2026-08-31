from __future__ import annotations

from typing import Protocol

from atlanticus.web.observability.models import WebEvent


class WebEventSink(Protocol):
    def emit(self, event: WebEvent) -> None: ...
