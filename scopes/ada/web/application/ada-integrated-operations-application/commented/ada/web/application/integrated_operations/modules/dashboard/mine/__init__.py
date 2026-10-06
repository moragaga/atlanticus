# Expone la frontera pública de Mine sin trasladar ownership de sus bindings al Dashboard raíz.
from ada.web.application.integrated_operations.modules.dashboard.mine.bindings import (
    CARGUIO_TRANSPORTE,
    MINE_COMPONENTS,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.layout import (
    build_mine_layout,
)

__all__ = [
    'CARGUIO_TRANSPORTE',
    'MINE_COMPONENTS',
    'build_mine_layout',
]
