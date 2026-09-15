from __future__ import annotations

from typing import Protocol, runtime_checkable

from atlanticus.web.manager.projection import DraftValidationResult


@runtime_checkable
class DraftValidationWorkflow(Protocol):
    def validate_draft(self, payload: dict[str, object]) -> DraftValidationResult: ...
