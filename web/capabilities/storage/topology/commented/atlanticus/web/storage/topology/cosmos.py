from __future__ import annotations

from dataclasses import dataclass

from atlanticus.web.storage.topology.errors import StorageTopologyConfigurationError


# Describe únicamente la forma física de un contenedor Cosmos; el nombre vive en el contrato genérico.
@dataclass(frozen=True, slots=True)
class CosmosContainerTopology:
    partition_key_path: str
    default_ttl_seconds: int | None = None

    def __post_init__(self) -> None:
        # La topología falla antes de cualquier llamada al provider si el partition key no es un path válido.
        partition_key_path = self.partition_key_path
        if not isinstance(partition_key_path, str):
            raise StorageTopologyConfigurationError('partition_key_path must be text')
        if partition_key_path != partition_key_path.strip():
            raise StorageTopologyConfigurationError(
                'partition_key_path must not contain surrounding whitespace'
            )
        if (
            not partition_key_path.startswith('/')
            or partition_key_path == '/'
            or '//' in partition_key_path
        ):
            raise StorageTopologyConfigurationError(
                'partition_key_path must be an absolute Cosmos JSON path'
            )
        if '\x00' in partition_key_path:
            raise StorageTopologyConfigurationError(
                'partition_key_path must not contain null characters'
            )
        # Repite deliberadamente la semántica del bridge objetivo: None, -1 o TTL positivo.
        ttl = self.default_ttl_seconds
        if ttl is not None and (
            not isinstance(ttl, int) or isinstance(ttl, bool) or ttl == 0 or ttl < -1
        ):
            raise StorageTopologyConfigurationError(
                'default_ttl_seconds must be None, -1, or a positive integer'
            )
