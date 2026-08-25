import pytest

from atlanticus.web.errors import WebConfigurationError
from atlanticus.web.hosting import resolve_gunicorn_capacity


def test_gunicorn_capacity_accepts_explicit_overrides():
    capacity = resolve_gunicorn_capacity(
        {'ATLANTICUS_WEB_WORKERS': '2', 'ATLANTICUS_WEB_THREADS': '4'}
    )

    assert capacity.workers == 2
    assert capacity.threads == 4


def test_gunicorn_capacity_rejects_invalid_overrides():
    with pytest.raises(WebConfigurationError, match='ATLANTICUS_WEB_WORKERS'):
        resolve_gunicorn_capacity({'ATLANTICUS_WEB_WORKERS': '0'})
