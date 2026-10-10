from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from dash import Input, Output, html, page_container

from atlanticus.web.application import create_web_application
from atlanticus.web.compositions.deployment_access_manager import (
    ROOT_LOGIN_PATH,
    ROOT_LOGOUT_PATH,
    ROOT_STATUS_PATH,
    DeploymentRootSession,
    RootManagerRequestScope,
    compose_root_manager_principal,
    create_deployment_access_manager_entry,
    create_deployment_root_http_module,
)
from atlanticus.web.deployment_access import (
    DeploymentAccessService,
    LocalDeploymentAccessStorage,
)
from atlanticus.web.identity.errors import IdentityAuthenticationError
from atlanticus.web.identity.module import create_identity_module
from atlanticus.web.identity.provider import IdentityProvider
from atlanticus.web.manager import (
    ManagerModuleGroup,
    ManagerPrincipal,
    ManagerSurface,
    ManagerSurfaceDefinition,
)
from atlanticus.web.models import ApplicationMetadata, WebApplicationDefinition
from atlanticus.web.modules import WebModule

_PASSWORD = 'root-password-for-integration-2026'


class NoOperationalIdentity(IdentityProvider):
    @property
    def key(self) -> str:
        return 'qualification-denied'

    @property
    def production_ready(self) -> bool:
        return False

    def validate_configuration(self) -> None:
        return None

    def resolve(self, _request):
        raise IdentityAuthenticationError('No operational identity in qualification')


def _pages(tmp_path: Path, monkeypatch) -> str:
    package_name = f'root_qualification_pages_{uuid4().hex}'
    package = tmp_path / package_name
    package.mkdir()
    (package / '__init__.py').write_text('', encoding='utf-8')
    route = f'/{package_name}'
    (package / 'home.py').write_text(
        'from dash import html, register_page\n'
        f'register_page(__name__, path={route!r}, name="Qualification")\n'
        'layout = html.Div("Qualification")\n',
        encoding='utf-8',
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    return package_name


def _csrf(response) -> str:
    match = re.search(r'name="csrf_token" value="([\w-]+)"', response.get_data(as_text=True))
    assert match is not None
    return match.group(1)


def _sign_in(client, *, password: str = _PASSWORD) -> None:
    token = _csrf(client.get(ROOT_LOGIN_PATH))
    result = client.post(
        ROOT_LOGIN_PATH,
        data={'csrf_token': token, 'service_user': 'root', 'password': password},
    )
    assert result.status_code == 303
    assert result.headers['Location'] == ROOT_STATUS_PATH


def _invoke_callback(client, callback: dict, *, value: object = 1):
    output = callback['output']
    assert isinstance(output, str) and output.endswith('.children')
    component_id = output.removesuffix('.children')
    inputs = callback['inputs']
    assert len(inputs) == 1
    source = inputs[0]
    return client.post(
        '/_dash-update-component',
        json={
            'output': output,
            'outputs': {'id': component_id, 'property': 'children'},
            'inputs': [
                {
                    'id': source['id'],
                    'property': source['property'],
                    'value': value,
                }
            ],
            'state': [],
            'changedPropIds': [f'{source["id"]}.{source["property"]}'],
        },
    )


def test_real_web_host_root_manager_isolation_and_material_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv('ATLANTICUS_ENVIRONMENT', 'local')
    page_package = _pages(tmp_path, monkeypatch)
    storage = LocalDeploymentAccessStorage(tmp_path / 'deployment-root.zip')
    access = DeploymentAccessService(
        storage=storage, application_namespace='qualification', environment='local'
    )
    access.bootstrap_initial(service_user='root', password=_PASSWORD)
    time = [datetime.now(UTC)]
    root = DeploymentRootSession(access=access, ttl_seconds=60, clock=lambda: time[0])

    def ordinary_principal() -> ManagerPrincipal:
        return ManagerPrincipal(subject_id='ordinary', display_name='Ordinary')

    principal = compose_root_manager_principal(root_session=root, fallback=ordinary_principal)
    entry = create_deployment_access_manager_entry(
        root_session=root, principal_provider=principal, group_key='administration'
    )
    surface = ManagerSurface(
        ManagerSurfaceDefinition(
            principal_provider=principal,
            groups=(ManagerModuleGroup(key='administration', title='Administración', order=0),),
            modules=(),
            entries=(entry,),
            route_prefix='/manager',
        )
    )
    scope = RootManagerRequestScope(root_session=root, manager_surface=surface)

    def register_private_callback(app, _services):
        @app.callback(
            Output('qualification-private-data', 'children'),
            Input('qualification-private-trigger', 'n_clicks'),
        )
        def private_callback(_clicks):
            return 'PRIVATE_OPERATIONAL_DATA'

    def register_private_routes(server, _services):
        server.add_url_rule(
            '/api/private',
            endpoint='qualification_private_data',
            view_func=lambda: 'PRIVATE_OPERATIONAL_DATA',
            methods=['GET'],
        )

    operational = WebModule(
        name='qualification-operational',
        register_routes=register_private_routes,
        register_callbacks=register_private_callback,
    )
    runtime = create_web_application(
        WebApplicationDefinition(
            import_name='root_qualification_web',
            metadata=ApplicationMetadata(
                application_id='root-qualification-web',
                display_name='ROOT Qualification',
                version='0.1.0',
            ),
            publications_root=tmp_path / 'publications',
            layout=lambda _services: html.Div(
                [
                    html.Button('Private', id='qualification-private-trigger'),
                    html.Div(id='qualification-private-data'),
                    page_container,
                ]
            ),
            page_packages=(page_package,),
            flask_config={'SECRET_KEY': 'qualification-only-session-secret'},
            modules=(
                create_identity_module(
                    NoOperationalIdentity(),
                    independent_routes=(ROOT_LOGIN_PATH, ROOT_STATUS_PATH, ROOT_LOGOUT_PATH),
                    alternative_request_authorizer=scope.authorize,
                ),
                create_deployment_root_http_module(
                    root_session=root,
                    allow_login_attempt=lambda address: address == '127.0.0.1',
                ),
                operational,
                *scope.manager_web_modules(),
                scope.guard_module(),
            ),
        )
    )
    client = runtime.server.test_client()
    stranger = runtime.server.test_client()

    assert client.get('/health/live').status_code == 200
    assert client.get('/manager').status_code == 401
    assert client.get('/_dash-layout').status_code == 401
    assert stranger.get(ROOT_STATUS_PATH).status_code == 401
    _sign_in(client)

    assert client.get(ROOT_STATUS_PATH).status_code == 200
    assert stranger.get('/manager').status_code == 401
    assert client.get('/manager').status_code == 200
    assert client.get('/manager/deployment-access').status_code == 200
    assert client.get('/manager/unknown').status_code == 401
    assert client.get('/').status_code == 401
    assert client.get('/api/private').status_code == 401

    layout = client.get('/_dash-layout')
    assert layout.status_code == 200
    assert layout.headers['Cache-Control'] == 'private, no-store'
    assert 'atlanticus-manager' in layout.get_data(as_text=True)
    assert 'qualification-private-data' not in layout.get_data(as_text=True)

    dependencies_response = client.get('/_dash-dependencies')
    assert dependencies_response.status_code == 200
    dependencies = dependencies_response.get_json()
    assert isinstance(dependencies, list)
    assert dependencies
    assert all(item['output'] != 'qualification-private-data.children' for item in dependencies)
    callback = next(
        item
        for item in dependencies
        if item['output'].endswith('deployment-access-status.children')
    )
    refreshed = _invoke_callback(client, callback)
    assert refreshed.status_code == 200
    assert 'Material ROOT: PRESENT y verificado.' in refreshed.get_data(as_text=True)
    assert (
        _invoke_callback(
            client,
            {
                'output': 'qualification-private-data.children',
                'inputs': [{'id': 'qualification-private-trigger', 'property': 'n_clicks'}],
            },
        ).status_code
        == 401
    )

    access.create_or_replace(service_user='root', password=_PASSWORD)
    assert client.get('/manager').status_code == 401
    assert client.get('/_dash-layout').status_code == 401
    assert _invoke_callback(client, callback).status_code == 401
    assert client.get(ROOT_STATUS_PATH).status_code == 401
    _sign_in(client)
    assert client.get('/manager/deployment-access').status_code == 200

    time[0] += timedelta(seconds=61)
    assert client.get('/manager').status_code == 401
    assert _invoke_callback(client, callback).status_code == 401
    _sign_in(client)
    status = client.get(ROOT_STATUS_PATH)
    assert status.status_code == 200
    token = _csrf(status)
    logout = client.post(ROOT_LOGOUT_PATH, data={'csrf_token': token})
    assert logout.status_code == 303
    assert logout.headers['Location'] == ROOT_LOGIN_PATH
    assert client.get('/manager').status_code == 401
    assert _invoke_callback(client, callback).status_code == 401
    assert client.get(ROOT_STATUS_PATH).status_code == 401
