import pytest

pytest.importorskip('dash')

from atlanticus.web.manager import ManagerModule, ManagerModuleGroup
from atlanticus.web.manager.projection import ProjectionState
from atlanticus.web.manager.registry import ManagerModuleRegistry
from atlanticus.web.manager.web.home import (
    HOME_PAGE_SIZE,
    build_home_page_content,
    build_manager_home,
    paginate_home_modules,
)
from atlanticus.web.manager.web.ids import (
    HOME_NEXT_ID,
    HOME_PAGE_LABEL_ID,
    HOME_PAGE_STORE_ID,
    HOME_PREVIOUS_ID,
)


def _layout(_services):
    return None


def _modules(count: int) -> tuple[ManagerModule, ...]:
    return tuple(
        ManagerModule(
            key=f'module-{index}',
            group_key='configuration',
            title=f'Módulo {index}',
            route=f'/module-{index}',
            order=index,
            layout=_layout,
            workflow_service=f'module-{index}.workflow',
            description=f'Configuración {index}',
        )
        for index in range(1, count + 1)
    )


def _registry(count: int) -> ManagerModuleRegistry:
    return ManagerModuleRegistry(
        groups=(ManagerModuleGroup('configuration', 'Configuraciones', 10),),
        modules=_modules(count),
        route_prefix='/manager',
    )


def test_home_paginates_six_modules_without_backend_contract() -> None:
    modules = _modules(7)

    first, page, page_count = paginate_home_modules(modules, 1)
    second, second_page, second_page_count = paginate_home_modules(modules, 2)

    assert HOME_PAGE_SIZE == 6
    assert tuple(module.key for module in first) == tuple(
        f'module-{index}' for index in range(1, 7)
    )
    assert tuple(module.key for module in second) == ('module-7',)
    assert (page, page_count) == (1, 2)
    assert (second_page, second_page_count) == (2, 2)


def test_home_keeps_pagination_visible_and_disabled_on_single_page() -> None:
    registry = _registry(3)
    modules = registry.modules

    cards, label, previous_disabled, next_disabled, page = build_home_page_content(
        registry=registry,
        modules=modules,
        states={module.key: ProjectionState.SYNCHRONIZED for module in modules},
        page=1,
    )

    assert len(cards) == 3
    assert label == '1 / 1'
    assert previous_disabled is True
    assert next_disabled is True
    assert page == 1


def test_home_layout_exposes_pagination_controls_even_with_one_page() -> None:
    registry = _registry(1)
    layout = build_manager_home(
        registry=registry,
        modules=registry.modules,
        states={},
    )

    component_ids = _component_ids(layout)

    assert HOME_PAGE_STORE_ID in component_ids
    assert HOME_PREVIOUS_ID in component_ids
    assert HOME_PAGE_LABEL_ID in component_ids
    assert HOME_NEXT_ID in component_ids


def _component_ids(component: object) -> set[str]:
    found: set[str] = set()
    component_id = getattr(component, 'id', None)
    if isinstance(component_id, str):
        found.add(component_id)
    children = getattr(component, 'children', None)
    if isinstance(children, (list, tuple)):
        for child in children:
            if child is not None:
                found.update(_component_ids(child))
    elif children is not None and not isinstance(children, str):
        found.update(_component_ids(children))
    return found
