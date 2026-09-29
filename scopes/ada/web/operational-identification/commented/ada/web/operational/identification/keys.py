# Las claves lógicas de Source separan el catálogo compartido de cada asignación individual.
from __future__ import annotations

from ada.web.operational.identification.errors import OperationalIdentificationError
from ada.web.operational.identification.models import validate_user_id
from atlanticus.web.source.models import SourceKey

CATALOG_SOURCE_KEY = SourceKey('ada-operational-catalog')
_ASSIGNMENT_PREFIX = 'ada-operational-user:'


# Se deriva la misma clave desde user_id de Atlanticus, no desde el correo.
def assignment_source_key(user_id: str) -> SourceKey:
    return SourceKey(_ASSIGNMENT_PREFIX + validate_user_id(user_id))


# Las claves inválidas no pueden tratarse como datos del dominio.
def source_kind(source_key: SourceKey) -> tuple[str, str | None]:
    if source_key == CATALOG_SOURCE_KEY:
        return 'catalog', None
    if source_key.value.startswith(_ASSIGNMENT_PREFIX):
        user_id = source_key.value[len(_ASSIGNMENT_PREFIX) :]
        try:
            return 'assignment', validate_user_id(user_id)
        except OperationalIdentificationError:
            pass
    raise OperationalIdentificationError('Source key is not owned by ADA operational data')
