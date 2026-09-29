from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ada.web.application.configuration_manager.operational_callbacks import (
    register_operational_callbacks,
)
from ada.web.application.configuration_manager.operational_layout import (
    _position_options,
    build_operational_manager_layout,
)
from ada.web.operational.identification import OperationalIdentificationService
from atlanticus.web.assets import AssetLayer
from atlanticus.web.manager import ManagerEntry, ManagerPrincipal
from atlanticus.web.modules import WebModule
from atlanticus.web.users.models import UserRecord

OPERATIONAL_MANAGER_ACCESS_KEY = 'operational.manage'
# Los estilos y assets son propiedad exclusiva de esta capacidad de ADA.
OPERATIONAL_MANAGER_ASSETS = AssetLayer(
    name='ada_configuration_manager_operational',
    load_order=740,
    package='ada.web.application.configuration_manager',
    resource_directory='resources/operational',
)


@dataclass(frozen=True, slots=True)
class OperationalManagerContext:
    service: OperationalIdentificationService
    promoted_users: Callable[[], tuple[UserRecord, ...]]
    principal: Callable[[], ManagerPrincipal]
    # Nombres de los providers resueltos por la composición anfitriona.
    source_name: str = 'Source'
    projection_name: str = 'Projection'

    def can_manage(self) -> bool:
        return OPERATIONAL_MANAGER_ACCESS_KEY in self.principal().access_keys


# El entry se integra en el registro normal de Manager y exige la clave funcional.
def create_operational_manager_entry(context: OperationalManagerContext) -> ManagerEntry:
    return ManagerEntry(
        key='operational-identification',
        group_key='administration',
        title='Datos operacionales',
        route='/operational-identification',
        order=15,
        description='Cargos y asignaciones operacionales de usuarios promovidos.',
        layout=lambda _services: build_operational_manager_layout(context),
        access_key=OPERATIONAL_MANAGER_ACCESS_KEY,
        web_module=WebModule(
            name='ada-operational-identification-manager',
            asset_layers=(OPERATIONAL_MANAGER_ASSETS,),
            register_callbacks=lambda app, _services: register_operational_callbacks(app, context),
        ),
    )


__all__ = [
    'OPERATIONAL_MANAGER_ACCESS_KEY',
    'OperationalManagerContext',
    '_position_options',
    'build_operational_manager_layout',
    'create_operational_manager_entry',
    'register_operational_callbacks',
]
