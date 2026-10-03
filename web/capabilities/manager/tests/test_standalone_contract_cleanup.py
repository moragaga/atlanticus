from __future__ import annotations

from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_SOURCE_ROOT = _PACKAGE_ROOT / 'src' / 'atlanticus' / 'web' / 'manager'
_COMMENTED_ROOT = _PACKAGE_ROOT / 'commented' / 'atlanticus' / 'web' / 'manager'


def test_manager_capability_has_no_standalone_application_runtime() -> None:
    assert not (_SOURCE_ROOT / 'application.py').exists()
    assert not (_SOURCE_ROOT / 'pages').exists()
