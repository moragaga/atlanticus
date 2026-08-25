from __future__ import annotations

# Modela solo anomalías web; no reutiliza executions/iterations de la observabilidad backend.

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class WebSeverity(StrEnum):
    WARNING = 'warning'
    ERROR = 'error'
    CRITICAL = 'critical'


@dataclass(frozen=True, slots=True)
class WebErrorInfo:
    type: str
    message: str


@dataclass(frozen=True, slots=True)
class WebEvent:
    name: str
    severity: WebSeverity
    message: str
    application: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    context: dict[str, Any] = field(default_factory=dict)
    error: WebErrorInfo | None = None
