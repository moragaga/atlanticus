from __future__ import annotations

from importlib.resources import files


def test_core_has_no_ui_or_time_status_dependencies() -> None:
    package = files('ada.web.content_state.core')
    source = '\n'.join(
        package.joinpath(filename).read_text(encoding='utf-8')
        for filename in ('__init__.py', 'freshness.py', 'models.py')
    )

    assert 'ada.web.ui' not in source
    assert 'dash' not in source.lower()
    assert 'time_status' not in source.lower()
    assert 'pi' not in source.lower()
    assert 'dispatch' not in source.lower()
