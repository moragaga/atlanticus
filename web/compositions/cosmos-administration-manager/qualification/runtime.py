from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from dash import html, page_container
from flask import Request

from atlanticus.web.application import create_web_application
from atlanticus.web.compositions.cosmos_administration_manager import (
    create_authenticated_root_provider,
    create_cosmos_root_manager_surface,
)
from atlanticus.web.compositions.deployment_access_manager import (
    ROOT_INDEPENDENT_ROUTES,
    DeploymentRootSession,
    RootManagerAccess,
    RootManagerRequestScope,
    create_deployment_root_http_module,
)
from atlanticus.web.cosmos_administration import CosmosAdministrationService
from atlanticus.web.deployment_access import DeploymentAccessService, LocalDeploymentAccessStorage
from atlanticus.web.identity.errors import IdentityAuthenticationError
from atlanticus.web.identity.local.provider import LocalIdentityProvider
from atlanticus.web.identity.models import AuthenticatedIdentity
from atlanticus.web.identity.module import create_identity_module
from atlanticus.web.identity.provider import IdentityProvider
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.models import (
    ApplicationMetadata,
    WebApplicationDefinition,
    WebApplicationRuntime,
)
from atlanticus.web.users.local import LOCAL_JANE, LOCAL_JOHN
from atlanticus.web.users.models import RuntimeUser
from atlanticus.web.users.store import UsersRuntimeStore

DEMO_USER = 'demo-root'
DEMO_PASSWORD = 'DemoRoot-Local-Only-2026'
_LOCAL_USERS = {'jane': LOCAL_JANE, 'john': LOCAL_JOHN}


class QualificationIdentityProvider(IdentityProvider):
    @property
    def key(self) -> str:
        return 'cosmos-qualification-operational-denied'

    @property
    def production_ready(self) -> bool:
        return False

    def validate_configuration(self) -> None:
        return None

    def resolve(self, _request: Request):
        raise IdentityAuthenticationError('Operational identity is disabled for ROOT qualification')


class QualificationUsersStore(UsersRuntimeStore):
    def __init__(self, user: RuntimeUser) -> None:
        self._user = user

    def resolve(self, identity: AuthenticatedIdentity) -> RuntimeUser | None:
        if (identity.issuer, identity.subject_id) == (self._user.issuer, self._user.subject_id):
            return self._user
        return None

    def list_users(self) -> tuple[RuntimeUser, ...]:
        return (self._user,)

    def replace_all(self, users: tuple[RuntimeUser, ...]) -> tuple[RuntimeUser, ...]:
        raise RuntimeError('Qualification users cannot be modified')


@dataclass(frozen=True, slots=True)
class QualificationRuntime:
    web: WebApplicationRuntime
    access: DeploymentAccessService


def build_qualification_runtime(
    *,
    directory: Path,
    administration: CosmosAdministrationService,
    local_user: str | None = None,
    local_users: UsersRuntimeStore | None = None,
) -> QualificationRuntime:
    if os.environ.get('ATLANTICUS_ENVIRONMENT', 'local').strip().lower() != 'local':
        raise ValueError('Cosmos ROOT qualification is only available in local environment')
    if not directory.is_absolute() or not directory.is_dir():
        raise ValueError('Qualification directory must be an existing absolute directory')
    if not isinstance(administration, CosmosAdministrationService):
        raise TypeError('Qualification requires CosmosAdministrationService')
    if local_user is not None and local_user not in _LOCAL_USERS:
        raise ValueError('Qualification local user must be jane or john')
    if local_users is not None and (
        local_user is None or not isinstance(local_users, UsersRuntimeStore)
    ):
        raise TypeError('Qualification local users require a valid local user selection')

    access = DeploymentAccessService(
        storage=LocalDeploymentAccessStorage(directory / 'qualification-root.zip'),
        application_namespace='atlanticus-cosmos-root-qualification',
        environment='local',
    )
    access.bootstrap_initial(service_user=DEMO_USER, password=DEMO_PASSWORD)
    root_session = DeploymentRootSession(access=access)

    def ordinary_principal() -> ManagerPrincipal:
        return ManagerPrincipal(subject_id='qualification-anonymous', display_name='Anonymous')

    identity_provider: IdentityProvider = QualificationIdentityProvider()
    authenticated_root = None
    if local_user is not None:
        selected = _LOCAL_USERS[local_user]
        identity_provider = LocalIdentityProvider(subject_id=selected.subject_id)
        authenticated_root = create_authenticated_root_provider(
            identity_provider=identity_provider,
            users=local_users or QualificationUsersStore(selected.to_runtime_user()),
        )
    root_access = RootManagerAccess(
        root_session=root_session,
        authenticated_root=authenticated_root,
    )
    surface = create_cosmos_root_manager_surface(
        root_session=root_session,
        administration=administration,
        fallback_principal=ordinary_principal,
        root_access=root_access,
    )
    scope = RootManagerRequestScope(
        root_session=root_session,
        manager_surface=surface,
        root_access=root_access,
        operational_access=(
            (lambda: authenticated_root() is not None)
            if authenticated_root is not None
            else None
        ),
    )
    web = create_web_application(
        WebApplicationDefinition(
            import_name='cosmos_root_qualification',
            metadata=ApplicationMetadata(
                application_id='cosmos-root-qualification',
                display_name='Atlanticus Cosmos ROOT Qualification',
                version='0.1.0',
            ),
            publications_root=directory / 'publications',
            layout=lambda _services: html.Div(page_container),
            page_packages=('qualification.pages',),
            flask_config={'SECRET_KEY': secrets.token_urlsafe(48)},
            modules=(
                create_identity_module(
                    identity_provider,
                    independent_routes=ROOT_INDEPENDENT_ROUTES,
                    alternative_request_authorizer=scope.authorize,
                ),
                create_deployment_root_http_module(
                    root_session=root_session,
                    allow_login_attempt=lambda address: address in {'127.0.0.1', '::1'},
                    manager_href=surface.registry.root_route,
                ),
                *scope.manager_web_modules(),
                scope.guard_module(),
            ),
        )
    )
    return QualificationRuntime(web=web, access=access)
