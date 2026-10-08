from ada.web.application.integrated_operations.modules.dashboard.card import (
    build_component_panel,
)
from ada.web.application.integrated_operations.modules.dashboard.mine.bindings import (
    TRANSPORTE,
)
from ada.web.content_state import ContentState, resolve_content_state


def _walk(node):
    yield node
    children = node.to_plotly_json()['props'].get('children')
    if not isinstance(children, (list, tuple)):
        children = () if children is None else (children,)
    for child in children:
        if hasattr(child, 'to_plotly_json'):
            yield from _walk(child)


def test_only_tiempos_y_colas_declares_construction() -> None:
    assert [card.key for card in TRANSPORTE.cards if card.content_state is ContentState.CONSTRUCTION] == [
        'tiempos_y_colas'
    ]
    assert all(
        card.content_state is ContentState.READY
        for card in TRANSPORTE.cards if card.key != 'tiempos_y_colas'
    )


def test_construction_survives_runtime_degradation() -> None:
    panel = build_component_panel(TRANSPORTE)
    wrappers = [
        node.to_plotly_json()['props']
        for node in _walk(panel)
        if node.to_plotly_json()['props'].get('data-ada-content-state-operational') == 'true'
    ]
    assert [props['data-ada-content-state-declared'] for props in wrappers] == [
        'ready', 'ready', 'construction'
    ]
    for runtime_state in (ContentState.STALE, ContentState.SOURCE_ERROR):
        assert resolve_content_state(ContentState.CONSTRUCTION, runtime_state) is ContentState.CONSTRUCTION
