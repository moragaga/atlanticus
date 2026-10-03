import pytest
from ada.contracts.tools.enums import ToolConfigurationKind as Kind

from ada_command_center.domain.alarms.routing_policy import next_routing_tool_kind


@pytest.mark.parametrize(
    ('source', 'expected'),
    [
        (Kind.PROCESS, Kind.INTEGRATED_OPERATIONS),
        (Kind.INTEGRATED_OPERATIONS, Kind.STRATEGIC),
        (Kind.STRATEGIC, None),
    ],
)
def test_next_routing_tool_kind_follows_strict_hierarchy(
    source: Kind, expected: Kind | None
) -> None:
    assert next_routing_tool_kind(source) is expected


@pytest.mark.parametrize('value', [None, 'process', 1])
def test_next_routing_tool_kind_rejects_non_tool_kinds(value: object) -> None:
    with pytest.raises(TypeError, match='ToolConfigurationKind'):
        next_routing_tool_kind(value)
