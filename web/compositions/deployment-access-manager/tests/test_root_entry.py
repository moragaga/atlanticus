from __future__ import annotations

import pytest
from flask import Flask

from atlanticus.web.compositions.deployment_access_manager import (
    DeploymentAccessManagerEntryError,
    DeploymentRootSession,
    compose_root_manager_principal,
    create_deployment_access_manager_entry,
)
from atlanticus.web.deployment_access import (
    DeploymentAccessAuthentication,
    DeploymentAccessIdentity,
    DeploymentAccessService,
    DeploymentAccessStatus,
    MaterialAvailability,
)
from atlanticus.web.manager import (
    DefaultManagerAuthorizationPolicy,
    ManagerModuleGroup,
    ManagerModuleRegistry,
    ManagerPrincipal,
)
from atlanticus.web.services import ServiceRegistry


class FakeAccess(DeploymentAccessService):
    def __init__(self) -> None:
        self.fingerprint = 'c' * 64
        self.inspect_calls = 0

    def authenticate(self, *, service_user, password):
        if (service_user, password) != ('root', 'correct-password-123'):
            raise ValueError('Invalid credentials')
        return DeploymentAccessAuthentication(
            identity=DeploymentAccessIdentity('f' * 32, 'root', 'test', 'local'),
            fingerprint=self.fingerprint,
        )

    def inspect(self):
        self.inspect_calls += 1
        return DeploymentAccessStatus(MaterialAvailability.PRESENT, self.fingerprint)


class FakeDash:
    def __init__(self) -> None:
        self.callbacks = []

    def callback(self, *_args, **_kwargs):
        def register(function):
            self.callbacks.append(function)
            return function

        return register


class DenyAll:
    def can_view(self, _principal, _item):
        return False


def _build(*, policy=None):
    flask = Flask(__name__)
    flask.secret_key = 'test-session-key'
    access = FakeAccess()
    root_session = DeploymentRootSession(access=access)
    principal = compose_root_manager_principal(
        root_session=root_session,
        fallback=lambda: ManagerPrincipal(subject_id='regular', display_name='Regular'),
    )
    entry = create_deployment_access_manager_entry(
        root_session=root_session,
        principal_provider=principal,
        group_key='administration',
        authorization=policy,
    )
    return flask, access, root_session, principal, entry


def _visible_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        return ' '.join(_visible_text(item) for item in value)
    children = getattr(value, 'children', None)
    return _visible_text(children) if children is not None else ''


def test_entry_integrates_with_manager_registry_and_uses_entry_lifecycle():
    flask, _access, root, principal, entry = _build()
    registry = ManagerModuleRegistry(
        (ManagerModuleGroup(key='administration', title='Administración', order=1),),
        (),
        entries=(entry,),
        route_prefix='/manager',
    )
    assert registry.route_for(entry) == '/manager/deployment-access'
    assert registry.require_entry('deployment-access') == entry
    with flask.test_request_context('/manager'):
        assert registry.visible_entries(principal(), DefaultManagerAuthorizationPolicy()) == ()
        root.login(service_user='root', password='correct-password-123')
        assert registry.visible_entries(principal(), DefaultManagerAuthorizationPolicy()) == (
            entry,
        )


def test_entry_does_not_inspect_material_without_verified_root():
    flask, access, root, _, entry = _build()
    with flask.test_request_context('/manager/deployment-access'):
        content = entry.layout(ServiceRegistry())
        assert 'Se requiere una sesión ROOT vigente' in _visible_text(content)
        assert access.inspect_calls == 0
        assert 'correct-password-123' not in _visible_text(content)
        assert access.fingerprint not in _visible_text(content)
        root.login(service_user='root', password='correct-password-123')
        current = entry.layout(ServiceRegistry())
        rendered = _visible_text(current)
        assert 'Material ROOT: PRESENT y verificado.' in rendered
        assert 'Usuario de servicio: root' in rendered
        assert 'Vigencia de sesión:' in rendered
        assert 'correct-password-123' not in rendered
        assert access.fingerprint not in rendered


def test_refresh_rechecks_root_session_after_material_rotation():
    flask, access, root, _, entry = _build()
    dash = FakeDash()
    entry.web_module.register_callbacks(dash, ServiceRegistry())
    assert len(dash.callbacks) == 1
    refresh = dash.callbacks[0]
    with flask.test_request_context('/_dash-update-component'):
        root.login(service_user='root', password='correct-password-123')
        assert 'Material ROOT: PRESENT' in _visible_text(refresh(1))
        access.fingerprint = 'd' * 64
        assert 'Se requiere una sesión ROOT vigente' in _visible_text(refresh(2))
        assert 'Material ROOT: PRESENT' not in _visible_text(refresh(2))


def test_root_session_alone_cannot_bypass_manager_authorization():
    flask, _access, root, _, entry = _build(policy=DenyAll())
    with flask.test_request_context('/manager/deployment-access'):
        root.login(service_user='root', password='correct-password-123')
        assert 'No tienes autorización' in _visible_text(entry.layout(ServiceRegistry()))


def _principal() -> ManagerPrincipal:
    return


def test_regular_administrative_override_is_not_equivalent_to_root_session():
    flask = Flask(__name__)
    flask.secret_key = 'test-session-key'
    access = FakeAccess()
    root_session = DeploymentRootSession(access=access)
    entry = create_deployment_access_manager_entry(
        root_session=root_session, principal_provider=_principal, group_key='administration'
    )
    with flask.test_request_context('/manager/deployment-access'):
        assert 'Se requiere una sesión ROOT vigente' in _visible_text(
            entry.layout(ServiceRegistry())
        )
        assert access.inspect_calls == 0


def test_invalid_entry_contracts_are_rejected():
    _, _, root, principal, _ = _build()
    with pytest.raises(DeploymentAccessManagerEntryError):
        create_deployment_access_manager_entry(
            root_session=object(), principal_provider=principal, group_key='administration'
        )
    with pytest.raises(DeploymentAccessManagerEntryError):
        create_deployment_access_manager_entry(
            root_session=root, principal_provider=None, group_key='administration'
        )


def test_outside_request_renders_no_material_state():
    _, access, _, _, entry = _build()
    assert 'requiere una solicitud autenticada' in _visible_text(entry.layout(ServiceRegistry()))
    assert access.inspect_calls == 0
