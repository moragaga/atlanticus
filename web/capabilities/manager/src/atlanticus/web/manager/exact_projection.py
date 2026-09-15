from typing import Protocol, runtime_checkable

from atlanticus.web.projection.models import (
    ProjectionExecutionResult,
    ProjectionTarget,
)


@runtime_checkable
class ExactProjectionWorkflow(Protocol):
    def get_current_projection_target(self) -> ProjectionTarget | None: ...

    def project(self, target: ProjectionTarget) -> ProjectionExecutionResult[object]: ...
