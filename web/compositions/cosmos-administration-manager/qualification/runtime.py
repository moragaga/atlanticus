from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from dash import html, page_container
from flask import Request

from atlanticus.web.application import create_web_application
from atlanticus.web.compositions.cosmos_administration_manager import (
    create_cosmos_root_manager_surface,
)
from atlanticus.web.compositions.deployment_access_manager import (
    ROOT_INDEPENDENT_ROUTES,
    DeploymentRootSession,
    RootManagerRequestScope,
    create_deployment_root_http_module,
)
from atlanticus.web.cosmos_administration import CosmosAdministrationService
from atlanticus.web.deployment_access import DeploymentAccessService, LocalDeploymentAccessStorage
from atlanticus.web.identity.errors import IdentityAuthenticationError
from atlanticus.web.identity.module import create_identity_module
from atlanticus.web.identity.provider import IdentityProvider
from atlanticus.web.manager import ManagerPrincipal
from atlanticus.web.models import (
    ApplicationMetadata,
    WebApplicationDefinition,
    WebApplicationRuntime,
)

DEMO_USER = 'demo-root'
DEMO_PASSWORD = 'DemoRoot-Local-Only-2026'


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


@dataclass(frozen=True, slots=True)
class QualificationRuntime:
    web: WebApplicationRuntime
    access: DeploymentAccessService


def build_qualification_runtime(
    *, directory: Path, administration: CosmosAdministrationService
) -> QualificationRuntime:
    if os.environ.get('ATLANTICUS_ENVIRONMENT', 'local').strip().lower() != 'local':
        raise ValueError('Cosmos ROOT qualification is only available in local environment')
    if not directory.is_absolute() or not directory.is_dir():
        raise ValueError('Qualification directory must be an existing absolute directory')
    if not isinstance(administration, CosmosAdministrationService):
        raise TypeError('Qualification requires CosmosAdministrationService')

    access = DeploymentAccessService(
        storage=LocalDeploymentAccessStorage(directory / 'qualification-root.zip'),
        application_namespace='atlanticus-cosmos-root-qualification',
        environment='local',
    )
    access.bootstrap_initial(service_user=DEMO_USER, password=DEMO_PASSWORD)
    root_session = DeploymentRootSession(access=access)

    def ordinary_principal() -> ManagerPrincipal:
        return ManagerPrincipal(subject_id='qualification-anonymous', display_name='Anonymous')

    surface = create_cosmos_root_manager_surface(
        root_session=root_session,
        administration=administration,
        fallback_principal=ordinary_principal,
    )
    scope = RootManagerRequestScope(root_session=root_session, manager_surface=surface)
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
                    QualificationIdentityProvider(),
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
