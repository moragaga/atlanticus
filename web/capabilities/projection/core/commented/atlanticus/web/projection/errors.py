from __future__ import annotations

from atlanticus.web.projection.models import ProjectionAttemptOutcome, ProjectionTarget


class ProjectionError(Exception):
    pass


# InvariantError señala que un provider incumplió un contrato ya validado por Core.
class ProjectionInvariantError(ProjectionError):
    pass


# Los providers concretos podrán especializar errores de persistencia bajo esta frontera.
class ProjectionStoreError(ProjectionError):
    pass


# Un fallo de ejecución conserva el target exacto para permitir retry sin republish de Source.
class ProjectionExecutionError(ProjectionError):
    outcome = ProjectionAttemptOutcome.FAILED

    def __init__(self, message: str, *, target: ProjectionTarget) -> None:
        super().__init__(message)
        self.target = target
