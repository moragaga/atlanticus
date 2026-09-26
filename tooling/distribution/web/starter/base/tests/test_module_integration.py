from __future__ import annotations

from application.composition import create_application_definition
from atlanticus.web.application import create_web_application


def test_example_module_registers_page_callback_and_assets(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    runtime = create_web_application(create_application_definition())

    assert runtime.server.test_client().get('/health/live').status_code == 200
    assert 'application.modules.example.pages.overview' in runtime.page_modules
    assert any('starter-example-result.children' in key for key in runtime.dash.callback_map)
    assert any('starter_example' in path for path in runtime.assets.css_entries)
