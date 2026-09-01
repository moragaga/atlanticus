from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NavigationCosmosContainerRequirement:
    container_name: str
    partition_key: str
    ttl_seconds: int | None = None


NAVIGATION_COSMOS_REQUIREMENTS = (
    NavigationCosmosContainerRequirement(
        container_name='configuration',
        partition_key='/partition_key',
    ),
)
