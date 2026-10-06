from dash import html

from ada.web.shell.header import (
    GLOBAL_INDICATORS_SLOT_ID,
    build_ada_operational_header,
)


def test_global_indicators_slot_exposes_stable_runtime_id() -> None:
    header = build_ada_operational_header(brand=html.Div('ADA'))
    row = header.children[0].children[0]
    slot = next(
        child
        for child in row.children
        if getattr(child, 'data-ada-slot-key', None) == 'global_indicators'
    )

    assert slot.id == GLOBAL_INDICATORS_SLOT_ID
    assert slot.children == []
    assert getattr(slot, 'data-slot-empty') == 'true'
