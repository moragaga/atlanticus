from dash import Input, Output

from ada.contracts.tools.enums import ToolConfigurationKind, ToolScope
from ada.contracts.tools.structure import ToolComponent, ToolStructure, ToolSubcomponent

from ada.web.alarms.collector import alarm_live_store_id
from ada.web.alarms.live_surface import ALARM_LIVE_BOARD_ID
from ada.web.application.integrated_operations.modules.dashboard.ids import DASHBOARD_ROOT_ID
from ada.web.application.integrated_operations.modules.dashboard.module import (
    create_dashboard_module,
)
from ada.web.application.integrated_operations.modules.dashboard.startup import (
    STARTUP_LOADER_INDEX,
    register_startup_alarm_readiness,
)
from ada.web.operational_render_binding import bind_operational_render


class DashStub:
    def __init__(self):
        self.arguments = None

    def clientside_callback(self, *arguments):
        self.arguments = arguments


def test_loader_not_mounted_without_operational_tool():
    module = create_dashboard_module(None)
    assert not module.index.body_start_fragments


def test_startup_alarm_readiness_wires_collector_store_to_dashboard():
    app = DashStub()
    register_startup_alarm_readiness(app, tool_key='integrated_operations')
    expression, output, store_input, board_input = app.arguments

    assert isinstance(expression, str)
    assert isinstance(output, Output)
    assert output.component_id == DASHBOARD_ROOT_ID
    assert output.component_property == 'data-ada-io-alarm-ready'
    assert isinstance(store_input, Input)
    assert store_input.component_id == alarm_live_store_id('integrated_operations')
    assert store_input.component_property == 'data'
    assert isinstance(board_input, Input)
    assert board_input.component_id == ALARM_LIVE_BOARD_ID
    assert board_input.component_property == 'style'


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
