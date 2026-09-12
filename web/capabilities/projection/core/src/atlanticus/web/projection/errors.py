from __future__ import annotations

from atlanticus.web.projection.models import ProjectionAttemptOutcome, ProjectionTarget


class ProjectionError(Exception):
    pass


class ProjectionInvariantError(ProjectionError):
    pass


class ProjectionStoreError(ProjectionError):
    pass


class ProjectionExecutionError(ProjectionError):
    outcome = ProjectionAttemptOutcome.FAILED

    def __init__(self, message: str, *, target: ProjectionTarget) -> None:
        super().__init__(message)
        self.target = target
