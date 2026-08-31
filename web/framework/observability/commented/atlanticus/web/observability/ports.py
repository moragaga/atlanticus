from __future__ import annotations

from typing import Protocol

from atlanticus.web.observability.models import WebEvent


# Puerto mínimo para conectar telemetría remota sin hacer que Web conozca Azure o Kernel.
class WebEventSink(Protocol):
    def emit(self, event: WebEvent) -> None: ...
