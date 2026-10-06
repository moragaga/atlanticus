# Espejo comentado: API pública del Operational Header.
from ada.web.shell.header.module import (
    ADA_OPERATIONAL_HEADER_ASSET_LAYER,
    create_ada_operational_header_module,
)
from ada.web.shell.header.presentation import (
    GLOBAL_INDICATORS_SLOT_ID,
    build_ada_operational_header,
)

__all__ = [
    'ADA_OPERATIONAL_HEADER_ASSET_LAYER',
    'GLOBAL_INDICATORS_SLOT_ID',
    'build_ada_operational_header',
    'create_ada_operational_header_module',
]
