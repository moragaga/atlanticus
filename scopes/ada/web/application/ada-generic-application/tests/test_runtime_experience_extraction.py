from __future__ import annotations

from importlib.util import find_spec

from ada.web.application.generic.application import create_application_definition
from ada.web.runtime_experience import ADA_SESSION_ASSET_LAYER, ADA_WAKE_LOCK_ASSET_LAYER


def test_generic_application_consumes_extracted_runtime_experience_package() -> None:
    definition = create_application_definition()
    modules = {module.name: module for module in definition.modules}

    assert modules['ada-session'].asset_layers == (ADA_SESSION_ASSET_LAYER,)
    assert modules['ada-wake-lock'].asset_layers == (ADA_WAKE_LOCK_ASSET_LAYER,)
    assert ADA_SESSION_ASSET_LAYER.package == 'ada.web.runtime_experience'
    assert ADA_WAKE_LOCK_ASSET_LAYER.package == 'ada.web.runtime_experience'


def test_legacy_application_runtime_modules_are_physically_removed() -> None:
    assert find_spec('ada.web.application.generic.session') is None
    assert find_spec('ada.web.application.generic.wake_lock') is None
