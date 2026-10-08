from __future__ import annotations

import pytest

from ada.web.ui.inline_row import (
    InlineComparisonRowDefinition,
    InlineComparisonRowState,
    InlineValueRowDefinition,
    InlineValueRowState,
    InlineValueRowTone,
    build_inline_comparison_row,
    build_inline_value_row,
)


def _text(component):
    if hasattr(component, 'to_plotly_json'):
        yield from _text(component.to_plotly_json()['props'].get('children'))
    elif isinstance(component, (list, tuple)):
        for child in component:
            yield from _text(child)
    elif component is not None:
        yield component


def test_inline_value_row_preserves_label_unit_and_value():
    result = build_inline_value_row(
        InlineValueRowState(
            definition=InlineValueRowDefinition(label='Rendimiento', unit='t/h'),
            value=1250,
            tone=InlineValueRowTone.DANGER,
            show_border=False,
        )
    )
    contents = tuple(_text(result))
    assert 'Rendimiento' in contents
    assert '(t/h)' in contents
    assert 1250 in contents


def test_inline_value_row_accepts_missing_unit_and_null_value():
    result = build_inline_value_row(
        InlineValueRowState(definition=InlineValueRowDefinition(label='Estado'), value=None)
    )
    assert tuple(_text(result)) == ('Estado',)


def test_comparison_preserves_both_values_and_separator():
    result = build_inline_comparison_row(
        InlineComparisonRowState(
            definition=InlineComparisonRowDefinition(label='Rendimiento', unit='t/h'),
            first_value='2450',
            second_value='2600',
            first_tone=InlineValueRowTone.WARNING,
            second_tone=InlineValueRowTone.DANGER,
        )
    )
    contents = tuple(_text(result))
    assert 'Rendimiento' in contents
    assert '(t/h)' in contents
    assert '2450' in contents
    assert '/' in contents
    assert '2600' in contents


def test_comparison_uses_consumer_supplied_separator():
    result = build_inline_comparison_row(
        InlineComparisonRowState(
            definition=InlineComparisonRowDefinition(label='Turno', separator='vs'),
            first_value=1,
            second_value=2,
        )
    )
    assert 'vs' in tuple(_text(result))


@pytest.mark.parametrize('definition', [InlineValueRowDefinition, InlineComparisonRowDefinition])
def test_row_definition_rejects_empty_label(definition):
    with pytest.raises(ValueError, match='label cannot be empty'):
        definition(label='')


def test_comparison_definition_rejects_missing_separator():
    with pytest.raises(ValueError, match='separator cannot be empty'):
        InlineComparisonRowDefinition(label='Turno', separator='')


def test_inline_row_state_rejects_invalid_tone_and_border_inputs():
    definition = InlineValueRowDefinition(label='Rendimiento')
    with pytest.raises(TypeError, match='tone'):
        InlineValueRowState(definition=definition, value=10, tone='danger')
    with pytest.raises(TypeError, match='show_border'):
        InlineValueRowState(definition=definition, value=10, show_border='false')


def test_comparison_row_requires_independent_valid_tones():
    definition = InlineComparisonRowDefinition(label='Rendimiento')
    with pytest.raises(TypeError, match='first_tone'):
        InlineComparisonRowState(
            definition=definition,
            first_value=10,
            second_value=20,
            first_tone='warning',
        )
    with pytest.raises(TypeError, match='second_tone'):
        InlineComparisonRowState(
            definition=definition,
            first_value=10,
            second_value=20,
            second_tone='danger',
        )
