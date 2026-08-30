from __future__ import annotations

from importlib.resources import files


def test_dependency_resolver_does_not_import_composition_time_status_or_dash() -> None:
    package = files('ada.web.content_state.dependency_resolver')
    source = '\n'.join(
        package.joinpath(filename).read_text(encoding='utf-8')
        for filename in ('__init__.py', 'errors.py', 'models.py', 'resolver.py')
    )

    assert 'tool_source_operational_participation' not in source
    assert 'ada.web.ui.time_status' not in source
    assert 'dash' not in source.lower()
    assert 'tool_key' not in source
    assert 'data-ada-' not in source


def test_dependency_resolver_has_no_named_control_source_catalog() -> None:
    package = files('ada.web.content_state.dependency_resolver')
    source = '\n'.join(
        package.joinpath(filename).read_text(encoding='utf-8')
        for filename in ('models.py', 'resolver.py')
    )

    assert '_CONTROL_SOURCE_KEYS' not in source
    assert "{'pi', 'dispatch'}" not in source
    assert "{'dispatch', 'pi'}" not in source
    assert "['pi', 'dispatch']" not in source
    assert "['dispatch', 'pi']" not in source
