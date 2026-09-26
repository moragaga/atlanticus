from __future__ import annotations

from pathlib import Path

from ada.web.application.generic import application


def test_custom_publications_root_is_accepted_by_installed_ada(monkeypatch, tmp_path):
    path = tmp_path / 'publications'
    monkeypatch.setenv('APPLICATION_PUBLICATIONS_ROOT', str(path))
    assert application.create_application_definition().publications_root == path


def test_default_publications_root_keeps_previous_behavior(monkeypatch):
    monkeypatch.delenv('APPLICATION_PUBLICATIONS_ROOT', raising=False)
    original = Path(application.__file__).resolve().parents[5] / '.runtime' / 'publications'
    assert application.create_application_definition().publications_root == original
