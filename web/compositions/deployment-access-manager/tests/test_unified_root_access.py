from __future__ import annotations

import pytest
from flask import Flask

from atlanticus.web.compositions.deployment_access_manager import (
    DeploymentRootSession,
    RootManagerAccess,
    RootManagerAccessError,
    compose_root_manager_principal,
    create_deployment_access_manager_entry,
)
from atlanticus.web.deployment_access import (
    DeploymentAccessAuthentication,
    DeploymentAccessIdentity,
    DeploymentAccessService,
    DeploymentAccessStatus,
    DeploymentAccessStorageError,
    MaterialAvailability,
)
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.services import ServiceRegistry


class FakeMaterial(DeploymentAccessService):
    def __init__(self):
        self.fingerprint = 'a' * 64
        self.unavailable = False

    def authenticate(self, *, service_user, password):
        if (service_user, password) != ('root', 'correct-password-for-testing'):
            raise ValueError('Invalid credentials')
        return DeploymentAccessAuthentication(
            DeploymentAccessIdentity('f' * 32, 'root', 'test', 'local'),
            self.fingerprint,
        )

    def inspect(self):
        if self.unavailable:
            raise DeploymentAccessStorageError('Storage unavailable')
        return DeploymentAccessStatus(MaterialAvailability.PRESENT, self.fingerprint)


def _local_root():
    return ManagerPrincipal(
        subject_id='local-jane',
        display_name='Jane',
        profile_label='Local',
        administrative_override=True,
        is_local=True,
    )


def test_material_and_authenticated_identity_are_independent():
    app = Flask(__name__)
    app.secret_key = 'test-only'
    material = FakeMaterial()
    root = DeploymentRootSession(access=material)
    access = RootManagerAccess(root_session=root, authenticated_root=_local_root)
    provider = compose_root_manager_principal(
        root_session=root,
        fallback=lambda: ManagerPrincipal(subject_id='ordinary', display_name='Ordinary'),
        root_access=access,
    )
    with app.test_request_context('/manager'):
        assert access.current().profile_label == 'Local'
        root.login(service_user='root', password='correct-password-for-testing')
        assert provider().profile_label == 'ROOT'
        root.logout()
        assert provider().profile_label == 'Local'
        material.unavailable = True
        assert provider().profile_label == 'Local'


def test_material_revocation_without_identity_fails_closed():
    app = Flask(__name__)
    app.secret_key = 'test-only'
    material = FakeMaterial()
    root = DeploymentRootSession(access=material)
    access = RootManagerAccess(root_session=root)
    with app.test_request_context('/manager'):
        assert access.current() is None
        root.login(service_user='root', password='correct-password-for-testing')
        assert access.current() is not None
        material.fingerprint = 'b' * 64
        assert access.current() is None


def test_untrusted_principal_cannot_claim_root():
    app = Flask(__name__)
    app.secret_key = 'test-only'
    root = DeploymentRootSession(access=FakeMaterial())
    access = RootManagerAccess(
        root_session=root,
        authenticated_root=lambda: ManagerPrincipal(subject_id='guest', display_name='Guest'),
    )
    with app.test_request_context('/manager'), pytest.raises(RootManagerAccessError):
        access.current()


def test_invalid_root_access_composition_is_rejected():
    root = DeploymentRootSession(access=FakeMaterial())
    other = DeploymentRootSession(access=FakeMaterial())
    access = RootManagerAccess(root_session=other, authenticated_root=_local_root)
    with pytest.raises(TypeError, match='matching ROOT access'):
        compose_root_manager_principal(
            root_session=root,
            fallback=lambda: ManagerPrincipal(subject_id='guest', display_name='Guest'),
            root_access=access,
        )


def _displayed_text(node):
    if isinstance(node, str):
        return node
    if isinstance(node, (list, tuple)):
        return ' '.join(_displayed_text(item) for item in node)
    return _displayed_text(node.children) if hasattr(node, 'children') else ''


@pytest.mark.parametrize(
    ('display_name', 'profile_label', 'is_local'),
    [
        ('Jane Doe', 'Local', True),
        ('John Doe', 'Local', True),
        ('Entra Administrator', 'Root', False),
    ],
)
def test_identity_root_entry_does_not_request_a_second_login(display_name, profile_label, is_local):
    app = Flask(__name__)
    app.secret_key = 'test-only'
    root = DeploymentRootSession(access=FakeMaterial())
    principal = ManagerPrincipal(
        subject_id='identity-admin',
        display_name=display_name,
        profile_label=profile_label,
        administrative_override=True,
        is_local=is_local,
    )
    access = RootManagerAccess(root_session=root, authenticated_root=lambda: principal)
    provider = compose_root_manager_principal(
        root_session=root,
        fallback=lambda: principal,
        root_access=access,
    )
    entry = create_deployment_access_manager_entry(
        root_session=root,
        principal_provider=provider,
        group_key='administration',
        root_access=access,
    )
    with app.test_request_context('/manager/deployment-access'):
        rendered = _displayed_text(entry.layout(ServiceRegistry()))
        assert 'Acceso administrativo ROOT activo.' in rendered
        assert f'Identidad: {display_name}.' in rendered
        assert f'Perfil: {profile_label}.' in rendered
        assert 'Autorización efectiva: ROOT.' in rendered
        assert 'No se requiere autenticación adicional.' in rendered
        assert 'Iniciar sesión con credenciales ROOT' not in rendered
        assert 'No hay una sesión de Deployment Access activa.' not in rendered


def test_independent_root_login_remains_available_when_not_authorized():
    app = Flask(__name__)
    app.secret_key = 'test-only'
    root = DeploymentRootSession(access=FakeMaterial())
    access = RootManagerAccess(root_session=root)
    entry = create_deployment_access_manager_entry(
        root_session=root,
        principal_provider=lambda: ManagerPrincipal(subject_id='ordinary', display_name='User'),
        group_key='administration',
        root_access=access,
    )
    with app.test_request_context('/manager/deployment-access'):
        rendered = _displayed_text(entry.layout(ServiceRegistry()))
        assert 'Iniciar sesión ROOT' in rendered
        assert 'Acceso administrativo ROOT activo.' not in rendered


def test_independent_root_session_retains_session_management_link():
    app = Flask(__name__)
    app.secret_key = 'test-only'
    root = DeploymentRootSession(access=FakeMaterial())
    access = RootManagerAccess(root_session=root)
    provider = compose_root_manager_principal(
        root_session=root,
        fallback=lambda: ManagerPrincipal(subject_id='ordinary', display_name='User'),
        root_access=access,
    )
    entry = create_deployment_access_manager_entry(
        root_session=root,
        principal_provider=provider,
        group_key='administration',
        root_access=access,
    )
    with app.test_request_context('/manager/deployment-access'):
        root.login(service_user='root', password='correct-password-for-testing')
        rendered = _displayed_text(entry.layout(ServiceRegistry()))
        assert 'Material ROOT: PRESENT y verificado.' in rendered
        assert 'Gestionar sesión ROOT y cerrar sesión' in rendered
        assert 'No se requiere autenticación adicional.' not in rendered
