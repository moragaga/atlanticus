from ada.web.configuration.manager_tools import build_manager_tools_page
from ada.web.configuration.tool_editor import TOOL_CONFIGURATION_EDITOR_ROOT_ID


def _component_ids(component) -> set[object]:
    ids: set[object] = set()
    component_id = getattr(component, 'id', None)
    if component_id is not None:
        ids.add(component_id)
    children = getattr(component, 'children', None)
    if children is None:
        return ids
    if isinstance(children, (list, tuple)):
        for child in children:
            if hasattr(child, 'children') or hasattr(child, 'id'):
                ids.update(_component_ids(child))
        return ids
    if hasattr(children, 'children') or hasattr(children, 'id'):
        ids.update(_component_ids(children))
    return ids


def test_manager_tools_composes_complete_tool_configuration_editor() -> None:
    page = build_manager_tools_page()

    assert TOOL_CONFIGURATION_EDITOR_ROOT_ID in _component_ids(page)
