# El API público expone únicamente el adapter durable; detalles de serialización quedan internos.
from atlanticus.web.users.cosmos.store import CosmosUsersRuntimeStore

__all__ = ['CosmosUsersRuntimeStore']
