import pytest

from ada.configuration.tools import ToolConfigurationKind, ToolScope
from ada.web.body.projection import (
    ToolBodyComponentBinding,
    ToolBodyProjection,
    ToolBodyProjectionError,
    ToolBodySubcomponentBinding,
)


def test_component_binding_rejects_non_deterministic_wrapper_id() -> None:
    with pytest.raises(ToolBodyProjectionError, match='wrapper id is invalid'):
        ToolBodyComponentBinding(
            tool_key='process',
            component_key='center_component',
            display_name='Center',
            scope=ToolScope.MINE,
            layout_role=None,
            wrapper_id='wrong',
            subcomponents=(),
        )


def test_subcomponent_binding_rejects_non_deterministic_wrapper_id() -> None:
    with pytest.raises(ToolBodyProjectionError, match='wrapper id is invalid'):
        ToolBodySubcomponentBinding(
            tool_key='process',
            owner_component_key='center_component',
            subcomponent_key='detail',
            display_name='Detail',
            linked_component_keys=(),
            wrapper_id='wrong',
        )


def test_projection_rejects_duplicate_component_wrappers() -> None:
    first = ToolBodyComponentBinding(
        tool_key='process',
        component_key='center_component',
        display_name='Center',
        scope=ToolScope.MINE,
        layout_role=None,
        wrapper_id='ada-tool-process-component-center_component',
        subcomponents=(),
    )
    with pytest.raises(ToolBodyProjectionError, match='component keys must be unique'):
        ToolBodyProjection(
            tool_key='process',
            kind=ToolConfigurationKind.PROCESS,
            root_id='ada-tool-process-body',
            components=(first, first),
        )
