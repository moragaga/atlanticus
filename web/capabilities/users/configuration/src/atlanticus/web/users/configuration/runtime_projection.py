from atlanticus.web.users.configuration.bundle import UsersConfigurationBundle
from atlanticus.web.users.configuration.contracts import (
    UsersProjectionRepository,
    UsersRuntimeProjectionWriter,
)
from atlanticus.web.users.configuration.projection import UsersProjectionState


class UsersRuntimeMaterializingProjectionRepository(UsersProjectionRepository):
    def __init__(
        self,
        *,
        runtime: UsersRuntimeProjectionWriter,
        projection: UsersProjectionRepository,
    ) -> None:
        self._runtime = runtime
        self._projection = projection

    def load_state(self) -> UsersProjectionState | None:
        return self._projection.load_state()

    def project(self, bundle: UsersConfigurationBundle, *, actor: str) -> UsersProjectionState:
        self._runtime.materialize(bundle, actor=actor)
        return self._projection.project(bundle, actor=actor)

    def health_check(self) -> bool:
        runtime_healthy = self._runtime.health_check()
        projection_healthy = self._projection.health_check()
        return runtime_healthy and projection_healthy
