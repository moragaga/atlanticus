# Capability mínima de validación de draft.
# Se separa del lifecycle monolítico para que dominios migrados no deban implementar
# operaciones de Source, proyección o history que no pertenecen a la validación.
from __future__ import annotations

from typing import Protocol, runtime_checkable

from atlanticus.web.manager.projection import DraftValidationResult


@runtime_checkable
class DraftValidationWorkflow(Protocol):
    def validate_draft(self, payload: dict[str, object]) -> DraftValidationResult: ...
