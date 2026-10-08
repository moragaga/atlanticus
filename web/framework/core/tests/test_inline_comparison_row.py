from __future__ import annotations

import pytest

from atlanticus.web.inline_comparison_row import (
    InlineComparisonRowDefinition,
    InlineComparisonRowState,
    build_inline_comparison_row,
)
from atlanticus.web.inline_value_row import InlineValueRowTone


def _props(component):
    return component.to_plotly_json()['props']


def _walk(component):
    yield component
    children = _props(component).get('children')
    if hasattr(children, 'to_plotly_json'):
        yield from _walk(children)
    elif isinstance(children, (list, tuple)):
        for child in children:
            if hasattr(child, 'to_plotly_json'):
                yield from _walk(child)


def test_inline_comparison_row_keeps_independent_tones() -> None:
    component = build_inline_comparison_row(
        InlineComparisonRowState(
            definition=InlineComparisonRowDefinition(
                label='Rendimiento',
                unit='t/h',
            ),
            first_value='2450',
            second_value='2600',
            first_tone=InlineValueRowTone.WARNING,
            second_tone=InlineValueRowTone.DANGER,
        )
    )
    classes = {
        _props(node).get('className')
        for node in _walk(component)
        if _props(node).get('className')
    }

    assert 'atlanticus-inline-comparison-row__value--warning' in ' '.join(classes)
    assert 'atlanticus-inline-comparison-row__value--danger' in ' '.join(classes)


def test_inline_comparison_row_definition_requires_non_empty_label() -> None:
    with pytest.raises(ValueError):
        InlineComparisonRowDefinition(label='')
