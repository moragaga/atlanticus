# Espejo pedagógico: esta composition integra Users con el shell Manager sin Source/Projection ficticios.
from atlanticus.web.compositions.users_manager.composition import (
    USERS_ADMINISTRATION_SERVICE,
    UsersManagerComposition,
    UsersPrincipalProvider,
    compose_users_manager,
)

__all__ = [
    'USERS_ADMINISTRATION_SERVICE',
    'UsersManagerComposition',
    'UsersPrincipalProvider',
    'compose_users_manager',
]
