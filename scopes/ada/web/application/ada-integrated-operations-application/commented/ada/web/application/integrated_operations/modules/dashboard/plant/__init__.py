# Expone la frontera pública de Plant sin trasladar ownership de sus bindings al Dashboard raíz.
from ada.web.application.integrated_operations.modules.dashboard.plant.bindings import (
    PLANT_COMPONENTS,
)
from ada.web.application.integrated_operations.modules.dashboard.plant.layout import (
    build_plant_layout,
)

__all__ = [
    'PLANT_COMPONENTS',
    'build_plant_layout',
]
