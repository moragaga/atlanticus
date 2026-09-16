# Espejo pedagógico del archivo productivo; conserva exactamente su comportamiento.
# Los comentarios en español describen responsabilidades sin alterar el contrato ejecutable.
from __future__ import annotations

import hashlib
import json

from atlanticus.web.navigation.configuration.models import NavigationConfigurationCatalog
from atlanticus.web.navigation.configuration.source_release import (
    NAVIGATION_SOURCE_RESOURCE_PATH,
    NavigationSourceCodec,
)
from atlanticus.web.source.models import SourceResource


# Operación: build_navigation_configuration_digest mantiene la misma semántica que el código productivo.
def build_navigation_configuration_digest(catalog: NavigationConfigurationCatalog) -> str:
    canonical = json.dumps(
        catalog.to_document(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    return hashlib.sha256(canonical).hexdigest()


# Operación: decode_navigation_configuration_import mantiene la misma semántica que el código productivo.
def decode_navigation_configuration_import(payload: bytes) -> NavigationConfigurationCatalog:
    resource = SourceResource(
        logical_path=NAVIGATION_SOURCE_RESOURCE_PATH,
        content=payload,
    )
    return NavigationSourceCodec().decode((resource,)).catalog
