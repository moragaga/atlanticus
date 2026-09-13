# Compone la materialización durable de Users con el repositorio que publica catálogo y estado.
# El estado de proyección sólo avanza después de que el runtime aceptó el snapshot completo.

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

    # El estado sigue perteneciendo al repositorio de proyección existente.
    def load_state(self) -> UsersProjectionState | None:
        return self._projection.load_state()

    def project(self, bundle: UsersConfigurationBundle, *, actor: str) -> UsersProjectionState:
        # Primero converge users.runtime. Si falla, el catálogo/estado activo no debe avanzar.
        self._runtime.materialize(bundle, actor=actor)
        return self._projection.project(bundle, actor=actor)

    def health_check(self) -> bool:
        # La superficie compuesta sólo está sana cuando ambas responsabilidades están disponibles.
        runtime_healthy = self._runtime.health_check()
        projection_healthy = self._projection.health_check()
        return runtime_healthy and projection_healthy
