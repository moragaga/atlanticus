import pytest
from pydantic import ValidationError

from atlanticus.web.configuration import WebSettings


def test_slow_request_threshold_defaults_to_two_seconds() -> None:
    assert WebSettings.from_mapping({}).slow_request_threshold_ms == 2000


def test_slow_request_threshold_is_configurable() -> None:
    assert WebSettings.from_mapping(
        {'ATLANTICUS_WEB_SLOW_REQUEST_THRESHOLD_MS': '3500'}
    ).slow_request_threshold_ms == 3500


@pytest.mark.parametrize('value', ('0', '-100', '1.5', 'not-a-number', 'true'))
def test_slow_request_threshold_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValidationError):
        WebSettings.from_mapping({'ATLANTICUS_WEB_SLOW_REQUEST_THRESHOLD_MS': value})
