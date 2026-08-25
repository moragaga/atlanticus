from flask import Flask, request

import atlanticus.web.identity.local.provider as provider_module
from atlanticus.web.identity.local import LocalIdentityProvider, create_local_identity_provider


def test_local_provider_keeps_explicit_subject_for_provider_lifetime() -> None:
    provider = LocalIdentityProvider(subject_id='local:test-user')
    server = Flask(__name__)

    with server.test_request_context('/'):
        first = provider.resolve(request)
        second = provider.resolve(request)

    assert first.provider_key == 'local'
    assert first.issuer == 'atlanticus-local'
    assert first.subject_id == 'local:test-user'
    assert second.subject_id == first.subject_id


def test_local_provider_uses_environment_subject(monkeypatch) -> None:
    monkeypatch.setenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', 'local:configured-user')

    provider = create_local_identity_provider()
    server = Flask(__name__)

    with server.test_request_context('/'):
        identity = provider.resolve(request)

    assert identity.subject_id == 'local:configured-user'


def test_local_provider_defaults_to_current_os_user(monkeypatch) -> None:
    monkeypatch.delenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID', raising=False)
    monkeypatch.setattr(provider_module.getpass, 'getuser', lambda: 'developer')

    provider = create_local_identity_provider()
    server = Flask(__name__)

    with server.test_request_context('/'):
        identity = provider.resolve(request)

    assert identity.subject_id == 'local:developer'


def test_local_provider_is_not_production_ready() -> None:
    assert LocalIdentityProvider(subject_id='local:test-user').production_ready is False
