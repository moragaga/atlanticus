# Define la frontera exacta de proyección que Manager consume sin traducir a contratos legacy.

from typing import Protocol, runtime_checkable

from atlanticus.web.projection.models import (
    ProjectionExecutionResult,
    ProjectionStatus,
    ProjectionTarget,
)


@runtime_checkable
class ExactProjectionWorkflow(Protocol):
    # Conserva ProjectionStatus de projection/core sin convertirlo al modelo legacy de Manager.
    def get_status(self) -> ProjectionStatus: ...

    # Devuelve el release exacto de Source que debe proyectarse en este momento.
    def get_current_projection_target(self) -> ProjectionTarget | None: ...

    # Proyecta ese target y conserva el resultado canónico de projection/core.
    def project(self, target: ProjectionTarget) -> ProjectionExecutionResult[object]: ...
