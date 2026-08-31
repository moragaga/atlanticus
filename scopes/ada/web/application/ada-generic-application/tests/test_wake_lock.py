from __future__ import annotations

from pathlib import Path

from ada.web.application.generic.application import create_application_definition
from ada.web.application.generic.wake_lock import (
    ADA_WAKE_LOCK_ASSET_LAYER,
    create_ada_wake_lock_module,
)


def test_wake_lock_module_has_independent_ada_asset_layer() -> None:
    module = create_ada_wake_lock_module()

    assert module.name == 'ada-wake-lock'
    assert module.asset_layers == (ADA_WAKE_LOCK_ASSET_LAYER,)
    assert ADA_WAKE_LOCK_ASSET_LAYER.name == 'ada_wake_lock'
    assert ADA_WAKE_LOCK_ASSET_LAYER.load_order == 9910
    assert ADA_WAKE_LOCK_ASSET_LAYER.package == 'ada.web.application.generic'
    assert ADA_WAKE_LOCK_ASSET_LAYER.resource_directory == 'resources/wake_lock'


def test_generic_application_composes_wake_lock_after_session() -> None:
    definition = create_application_definition()
    names = tuple(module.name for module in definition.modules)

    assert names.count('ada-wake-lock') == 1
    assert names.index('ada-wake-lock') > names.index('ada-session')


def test_wake_lock_javascript_stays_inside_ada_operational_runtime() -> None:
    source = (
        Path(__file__).parents[1]
        / 'src'
        / 'ada'
        / 'web'
        / 'application'
        / 'generic'
        / 'resources'
        / 'wake_lock'
        / 'js'
        / '10-screen-wake-lock.js'
    ).read_text(encoding='utf-8')

    assert "const OPERATIONAL_PATH = '/';" in source
    assert "navigator.wakeLock.request('screen')" in source
    assert "document.addEventListener('visibilitychange'" in source
    assert "window.addEventListener('pageshow'" in source
    assert "window.addEventListener('popstate'" in source
    assert 'pushState' in source
    assert 'replaceState' in source
    assert 'console.warn(UNSUPPORTED_MESSAGE)' in source
    assert 'console.error(REQUEST_ERROR_MESSAGE, error)' in source
    assert 'serviceWorker' not in source
    assert 'localStorage' not in source
    assert 'sessionStorage' not in source
    assert 'fetch(' not in source
    assert 'integrated_operations' not in source.lower()
    assert 'flotacion' not in source.lower()
    assert 'carguio' not in source.lower()
