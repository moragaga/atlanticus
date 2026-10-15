from ada.contracts.tools.enums import ToolConfigurationKind, ToolScope
from ada.contracts.tools.structure import ToolComponent, ToolStructure, ToolSubcomponent

from ada.web.application.integrated_operations.modules.dashboard.mine import (
    MINE_COMPONENTS,
)
from ada.web.application.integrated_operations.modules.dashboard.plant import (
    PLANT_COMPONENTS,
)
from ada.web.application.integrated_operations.modules.dashboard.card import (
    build_component_panel,
)
from ada.web.application.integrated_operations.modules.dashboard.module import (
    create_dashboard_module,
)
from ada.web.application.integrated_operations.modules.dashboard.startup import (
    STARTUP_LOADER_INDEX,
)
from ada.web.operational_render_binding import bind_operational_render


def test_loader_not_mounted_without_operational_tool():
    module = create_dashboard_module(None)
    assert not module.index.body_start_fragments


def test_all_operational_areas_begin_pending_first_render():
    areas = (*MINE_COMPONENTS, *PLANT_COMPONENTS)
    assert len(areas) == 9
    for area in areas:
        panel = build_component_panel(area)
        assert panel.to_plotly_json()['props']['data-ready'] == 'false'



def test_loader_is_attached_to_a_configured_integrated_dashboard():
    structure = ToolStructure(
        tool_key='integrated_operations',
        kind=ToolConfigurationKind.INTEGRATED_OPERATIONS,
        components=(
            ToolComponent(
                'mine_component', 'Mine',
                subcomponents=(ToolSubcomponent('mine_card', 'Mine Card'),),
                scope=ToolScope.MINE,
            ),
            ToolComponent(
                'plant_component', 'Plant',
                subcomponents=(ToolSubcomponent('plant_card', 'Plant Card'),),
                scope=ToolScope.PLANT,
            ),
        ),
    )
    module = create_dashboard_module(bind_operational_render(structure))
    assert module.index is STARTUP_LOADER_INDEX
