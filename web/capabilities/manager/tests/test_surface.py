import pytest

pytest.importorskip('dash')

from atlanticus.web.manager import (
    ManagerModule,
    ManagerModuleGroup,
    ManagerPrincipal,
    ManagerSurfaceDefinition,
)
from atlanticus.web.manager.surface import ManagerSurface
from atlanticus.web.services import ServiceRegistry


def _principal() -> ManagerPrincipal:
    return ManagerPrincipal(
        subject_id='local',
        display_name='Administrador local',
        is_local=True,
    )


def _layout(_services):
    return None


def _surface(route_prefix: str = '/manager') -> ManagerSurfaceDefinition:
    return ManagerSurfaceDefinition(
        principal_provider=_principal,
        groups=(ManagerModuleGroup('configuration', 'Configuraciones', 10),),
        modules=(
            ManagerModule(
                key='tools',
                group_key='configuration',
                title='Herramientas',
                route='/tools',
                order=10,
                layout=_layout,
                workflow_service='tools.workflow',
            ),
        ),
        default_module_key='tools',
        route_prefix=route_prefix,
    )


def test_manager_surface_is_host_independent_and_prefix_aware() -> None:
    surface = ManagerSurface(_surface())

    assert surface.default_path == '/manager/tools'
    assert surface.registry.root_route == '/manager'
    assert [module.name for module in surface.web_modules] == ['manager-surface']
    assert all(not module.page_packages for module in surface.web_modules)


def test_manager_surface_layout_does_not_render_standalone_header() -> None:
    surface = ManagerSurface(_surface())
    layout = surface.layout(ServiceRegistry())
    class_names = _class_names(layout)

    assert 'atlanticus-manager' in class_names
    assert 'atlanticus-manager--surface' in class_names
    assert 'atlanticus-manager__header' not in class_names
    assert 'atlanticus-manager__summary' in class_names
    assert 'atlanticus-manager__content' in class_names


def _class_names(component: object) -> set[str]:
    found: set[str] = set()
    class_name = getattr(component, 'className', None)
    if isinstance(class_name, str):
        found.update(class_name.split())
    children = getattr(component, 'children', None)
    if isinstance(children, (list, tuple)):
        for child in children:
            if child is not None:
                found.update(_class_names(child))
    elif children is not None and not isinstance(children, str):
        found.update(_class_names(children))
    return found
