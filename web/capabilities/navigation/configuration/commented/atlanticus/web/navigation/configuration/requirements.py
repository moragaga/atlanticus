from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NavigationCosmosContainerRequirement:
    # Contrato físico mínimo del contenedor que necesita Navigation.
    container_name: str
    partition_key: str
    ttl_seconds: int | None = None


# Navigation comparte el contenedor de configuración mediante una partition key genérica.
NAVIGATION_COSMOS_REQUIREMENTS = (
    NavigationCosmosContainerRequirement(
        container_name='configuration',
        partition_key='/partition_key',
    ),
)
