from __future__ import annotations

from importlib.resources import files


def test_content_state_has_no_ui_time_status_tool_or_dash_dependency() -> None:
    package = files('ada.web.content_state')
    source = '\n'.join(
        package.joinpath(filename).read_text(encoding='utf-8')
        for filename in (
            '__init__.py',
            'dependencies.py',
            'errors.py',
            'freshness.py',
            'models.py',
        )
    )

    assert 'ada.web.ui' not in source
    assert 'time_status' not in source.lower()
    assert 'ada.web.tools' not in source
    assert 'dash' not in source.lower()
    assert "{'pi', 'dispatch'}" not in source
    assert "{'dispatch', 'pi'}" not in source


def test_content_state_public_namespace_is_consolidated() -> None:
    import ada.web.content_state as content_state

    assert content_state.ContentState.READY.value == 'ready'
    assert content_state.ContentStateDependencyGraph is not None
