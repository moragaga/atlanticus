from __future__ import annotations

import pytest
from pydantic import ValidationError

from atlanticus.web.configuration import WebSettings


def test_web_port_defaults_to_8000_without_environment_variable(monkeypatch) -> None:
    monkeypatch.delenv('ATLANTICUS_WEB_PORT', raising=False)

    assert WebSettings().web_port == 8000
    assert WebSettings.from_mapping({}).web_port == 8000


def test_web_port_reads_environment_override(monkeypatch) -> None:
    monkeypatch.setenv('ATLANTICUS_WEB_PORT', '8051')

    assert WebSettings().web_port == 8051
    assert WebSettings.from_mapping({'ATLANTICUS_WEB_PORT': '9001'}).web_port == 9001


@pytest.mark.parametrize('value', ('0', '65536', '-1', 'wrong', ''))
def test_web_port_rejects_invalid_configuration(value: str) -> None:
    with pytest.raises(ValidationError):
        WebSettings.from_mapping({'ATLANTICUS_WEB_PORT': value})


def test_web_port_accepts_tcp_boundary_values() -> None:
    assert WebSettings.from_mapping({'ATLANTICUS_WEB_PORT': '1'}).web_port == 1
    assert WebSettings.from_mapping({'ATLANTICUS_WEB_PORT': '65535'}).web_port == 65535
