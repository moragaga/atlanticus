from __future__ import annotations

from dataclasses import dataclass

from ada.web.content_state.core import ContentState
from ada.web.ui.time_status import TimeStatusSummaryState


@dataclass(frozen=True, slots=True)
class AdaOperationalState:
    tool_key: str | None
    time_status_summary: TimeStatusSummaryState | None
    global_indicators_runtime_state: ContentState
    global_indicators_source_keys: tuple[str, ...]
