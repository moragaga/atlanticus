from __future__ import annotations

from dataclasses import dataclass

from ada.web.content_state import ContentState


@dataclass(frozen=True, slots=True)
class AdaOperationalState:
    tool_key: str | None
    global_indicators_runtime_state: ContentState
    global_indicators_source_keys: tuple[str, ...]
