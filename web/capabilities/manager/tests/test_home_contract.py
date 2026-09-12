from atlanticus.web.manager import (
    DefaultManagerAuthorizationPolicy,
    ManagerModule,
    ManagerModuleGroup,
    ManagerModuleRegistry,
    ManagerPrincipal,
    ManagerSurfaceDefinition,
)
from atlanticus.web.manager.web.home import build_manager_home_return
from atlanticus.web.manager.web.ids import CONTENT_ID, HOME_ID
from atlanticus.web.manager.web.layout import build_manager_surface
from atlanticus.web.services import ServiceRegistry


def _component_by_id(component: object, component_id: str) -> object | None:
    if getattr(component, 'id', None) == component_id:
        return component
    children = getattr(component, 'children', None)
    if isinstance(children, (list, tuple)):
        for child in children:
            if child is None:
                continue
            found = _component_by_id(child, component_id)
            if found is not None:
                return found
    elif children is not None and not isinstance(children, str):
        return _component_by_id(children, component_id)
    return None


def _surface():
    group = ManagerModuleGroup('configuration', 'Configuraciones', 10)
    module = ManagerModule(
        key='tools',
        group_key=group.key,
        title='Herramientas',
        route='/tools',
        order=10,
        layout=lambda _services: None,
        workflow_service='tools.workflow',
    )
    principal = ManagerPrincipal('local', 'Administrador local', is_local=True)
    definition = ManagerSurfaceDefinition(
        principal_provider=lambda: principal,
        groups=(group,),
        modules=(module,),
    )
    registry = ManagerModuleRegistry(definition.groups, definition.modules)
    return (
        build_manager_surface(
            definition=definition,
            registry=registry,
            services=ServiceRegistry(),
            principal=principal,
            authorization=DefaultManagerAuthorizationPolicy(),
        ),
        registry,
    )


def test_manager_home_and_module_content_are_distinct_runtime_slots() -> None:
    surface, _registry = _surface()

    home = _component_by_id(surface, HOME_ID)
    content = _component_by_id(surface, CONTENT_ID)

    assert home is not None
    assert content is not None
    assert home is not content


def test_module_pages_return_to_the_registry_root_route() -> None:
    _surface_component, registry = _surface()

    link = build_manager_home_return(registry.root_route)

    assert link.href == registry.root_route
