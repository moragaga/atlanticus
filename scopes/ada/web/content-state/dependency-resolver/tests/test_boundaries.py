from __future__ import annotations

from importlib.resources import files


def test_dependency_resolver_does_not_import_time_status_or_dash() -> None:
    package = files('ada.web.content_state.dependency_resolver')
    source = '\n'.join(
        package.joinpath(filename).read_text(encoding='utf-8')
        for filename in ('__init__.py', 'errors.py', 'models.py', 'resolver.py')
    )

    assert 'ada.web.ui.time_status' not in source
    assert 'dash' not in source.lower()
    assert 'tool_key' not in source
    assert 'data-ada-' not in source


def test_only_pi_and_dispatch_are_declared_as_control_sources() -> None:
    source = (
        files('ada.web.content_state.dependency_resolver')
        .joinpath('models.py')
        .read_text(encoding='utf-8')
    )

    assert "frozenset({'pi', 'dispatch'})" in source
    assert 'blockgrade' not in source.lower()
