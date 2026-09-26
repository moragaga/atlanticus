from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

import atlanticus.connectivity.http.client as client_module
from atlanticus.connectivity.http import (
    HttpAuthMode,
    HttpClient,
    HttpConfigurationError,
    HttpRequestError,
    HttpSettings,
)


def _token_settings(**overrides: object) -> HttpSettings:
    values: dict[str, object] = {
        'base_url': 'https://api.example.test/met/',
        'auth_mode': HttpAuthMode.TOKEN,
        'token': 'private-secret',
    }
    values.update(overrides)
    return HttpSettings(**values)


def _transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    original_client = httpx.Client

    def build(**kwargs: object) -> httpx.Client:
        return original_client(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(client_module.httpx, 'Client', build)


def test_token_mode_sends_exact_authorization_header_and_decodes_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        return httpx.Response(200, request=request, json={'datos': []})

    _transport(monkeypatch, handler)
    settings = _token_settings()

    with HttpClient(settings=settings) as client:
        payload = client.request_json('GET', 'consultas', params={'op': 'datos'})

    assert payload == {'datos': []}
    assert settings.token == 'private-secret'
    assert 'private-secret' not in repr(settings)
    assert received[0].headers['Authorization'] == 'Token private-secret'
    assert received[0].url.params['op'] == 'datos'
    assert len(received) == 1


@pytest.mark.parametrize(
    'overrides',
    (
        {'token': None},
        {'token': ''},
        {'token': 'Token private-secret'},
        {'token': 'private secret'},
        {'token': 'private\nsecret'},
        {'bearer_token': 'unique-bearer-canary-9824'},
        {
            'username': 'unique-basic-user-canary-9824',
            'password': 'unique-basic-password-canary-9824',
        },
    ),
)
def test_token_mode_rejects_missing_ambiguous_or_unsafe_credentials(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(HttpConfigurationError) as captured:
        _token_settings(**overrides)

    message = repr(captured.value)
    for secret in (
        'private-secret',
        'unique-bearer-canary-9824',
        'unique-basic-user-canary-9824',
        'unique-basic-password-canary-9824',
    ):
        assert secret not in message


@pytest.mark.parametrize(
    'auth_mode,credentials',
    (
        (HttpAuthMode.NONE, {}),
        (HttpAuthMode.BEARER, {'bearer_token': 'bearer-secret'}),
        (HttpAuthMode.BASIC, {'username': 'user', 'password': 'password'}),
    ),
)
def test_existing_authentication_modes_do_not_accept_token_credential(
    auth_mode: HttpAuthMode,
    credentials: dict[str, str],
) -> None:
    with pytest.raises(HttpConfigurationError):
        HttpSettings(
            base_url='https://api.example.test',
            auth_mode=auth_mode,
            token='private-secret',
            **credentials,
        )


def test_token_mode_cannot_override_authorization_from_a_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, request=request)

    _transport(monkeypatch, handler)
    with HttpClient(settings=_token_settings()) as client:
        with pytest.raises(HttpRequestError):
            client.request('GET', 'consultas', headers={'Authorization': 'Bearer override'})

    assert calls == []
