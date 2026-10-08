import pytest

from ada_command_center.web.tools.discovery_cosmos import (
    ToolCatalogConnectionStatus,
    ToolCatalogDiscovery,
    ToolCatalogDiscoveryError,
)

from .test_discovery import CosmosStub, _seed


def test_empty_declared_connection_blocks_confirmation_even_with_ready_tool():
    ready = CosmosStub()
    _seed(ready, namespace='mine', tool_key='mine')
    empty = CosmosStub()
    report = ToolCatalogDiscovery(connections={'mine': ready, 'other': empty}).inspect()
    assert {item.connection_name: item.status for item in report.connections} == {
        'mine': ToolCatalogConnectionStatus.READY,
        'other': ToolCatalogConnectionStatus.NO_TOOLS,
    }
    with pytest.raises(ToolCatalogDiscoveryError, match='not ready'):
        report.consolidation_inputs(current=None)
    assert ready.writes == 1
    assert empty.writes == 0
