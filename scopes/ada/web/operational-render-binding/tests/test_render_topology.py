import pytest

from ada.contracts.tools.enums import ToolConfigurationKind, ToolScope
from ada.contracts.tools.structure import ToolComponent, ToolStructure, ToolSubcomponent
from ada.web.operational_render_binding import (
    OperationalRenderBindingError,
    bind_operational_render,
)


def _component(key: str) -> ToolComponent:
    return ToolComponent(
        key=key,
        display_name=key.title(),
        subcomponents=(ToolSubcomponent(key=f'{key}_detail', display_name='Detalle'),),
    )


def _process_structure() -> ToolStructure:
    return ToolStructure(
        tool_key='process',
        kind=ToolConfigurationKind.PROCESS,
        operational_scope=ToolScope.PLANT,
        center_component_key='center',
        components=(
            _component('left'),
            _component('center'),
            _component('right'),
            _component('detail'),
        ),
    )


def test_binding_separates_optional_bottom_without_changing_structure_order() -> None:
    binding = bind_operational_render(
        _process_structure(),
        bottom_component_key='detail',
    )

    assert binding.component_keys == ('left', 'center', 'right', 'detail')
    assert binding.main_component_keys == ('left', 'center', 'right')
    assert binding.bottom_component_key == 'detail'
    assert binding.bottom_component is not None
    assert binding.bottom_component.component.key == 'detail'


def test_binding_without_bottom_keeps_all_components_in_main_row() -> None:
    binding = bind_operational_render(_process_structure())

    assert binding.main_component_keys == binding.component_keys
    assert binding.bottom_component is None


def test_binding_rejects_center_as_bottom() -> None:
    with pytest.raises(
        OperationalRenderBindingError,
        match='must differ from Process center component',
    ):
        bind_operational_render(
            _process_structure(),
            bottom_component_key='center',
        )


def test_binding_rejects_unknown_bottom_component() -> None:
    with pytest.raises(
        OperationalRenderBindingError,
        match='must reference a Tool component',
    ):
        bind_operational_render(
            _process_structure(),
            bottom_component_key='missing',
        )
