from dash.development.base_component import Component

from atlanticus.web.manager.web.layout import _history_empty_state


def _walk(component: object) -> list[Component]:
    found: list[Component] = []
    if isinstance(component, Component):
        found.append(component)
        children = getattr(component, 'children', None)
        if isinstance(children, (list, tuple)):
            for child in children:
                found.extend(_walk(child))
        elif children is not None:
            found.extend(_walk(children))
    return found


def test_history_empty_state_is_structured_and_explanatory() -> None:
    component = _history_empty_state()
    nodes = _walk(component)

    assert component.className == 'atlanticus-manager__history-empty'
    texts = {
        node.children
        for node in nodes
        if isinstance(getattr(node, 'children', None), str)
    }
    assert 'Aún no hay revisiones publicadas.' in texts
    assert any('primera publicación' in text for text in texts)
