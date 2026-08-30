from __future__ import annotations

import pytest

from ada.web.ui.content_state import (
    ContentState,
    resolve_content_state,
    resolve_content_state_visual,
)


def test_content_state_values_are_stable() -> None:
    assert tuple(state.value for state in ContentState) == (
        'ready',
        'stale',
        'source_error',
        'construction',
    )


def test_content_state_resolver_defaults_to_ready() -> None:
    assert resolve_content_state() is ContentState.READY


def test_content_state_resolver_applies_frozen_precedence() -> None:
    assert resolve_content_state(ContentState.READY, ContentState.STALE) is ContentState.STALE
    assert (
        resolve_content_state(ContentState.STALE, ContentState.SOURCE_ERROR)
        is ContentState.SOURCE_ERROR
    )
    assert (
        resolve_content_state(
            ContentState.SOURCE_ERROR,
            ContentState.CONSTRUCTION,
            ContentState.STALE,
        )
        is ContentState.CONSTRUCTION
    )


def test_content_state_resolver_rejects_implicit_string_coercion() -> None:
    with pytest.raises(TypeError, match='requires ContentState values'):
        resolve_content_state(ContentState.READY, 'stale')  # type: ignore[arg-type]


def test_content_state_visual_contract_is_explicit() -> None:
    assert resolve_content_state_visual(ContentState.READY) is None

    stale = resolve_content_state_visual(ContentState.STALE)
    source_error = resolve_content_state_visual(ContentState.SOURCE_ERROR)
    construction = resolve_content_state_visual(ContentState.CONSTRUCTION)

    assert stale is not None
    assert stale.message == 'Información desactualizada'
    assert stale.icon_class == 'bi bi-cloud-slash'
    assert source_error is not None
    assert source_error.message == 'Fuente de datos con error'
    assert source_error.icon_class == 'bi bi-exclamation-triangle-fill'
    assert construction is not None
    assert construction.message == 'En construcción'
    assert construction.icon_class == 'bi bi-hammer'
