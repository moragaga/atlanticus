# Superficie pública estable; evita acoplar consumidores a módulos internos.
from atlanticus.web.users.activity.adapters.cosmos import CosmosUserActivityRepository
from atlanticus.web.users.activity.adapters.memory import MemoryUserActivityRepository

__all__ = ['CosmosUserActivityRepository', 'MemoryUserActivityRepository']
