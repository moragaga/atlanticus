from __future__ import annotations

import argparse
import json
import os
import sys
from importlib import metadata
from pathlib import Path


# Un wheel interno instalado en editable invalida una calificación portable.
def _verify_dependencies(portable: bool) -> list[str]:
    errors: list[str] = []
    for distribution in metadata.distributions():
        name = (distribution.metadata.get('Name') or '').lower().replace('_', '-')
        if not name.startswith(('atlanticus-', 'ada-')):
            continue
        direct_url = distribution.read_text('direct_url.json')
        if direct_url is None:
            continue
        try:
            record = json.loads(direct_url)
        except ValueError:
            errors.append(f'Invalid installation metadata for {name}')
            continue
        if portable and name not in ('application-starter', 'ada-application-starter') and (
            record.get('dir_info', {}).get('editable') is True
        ):
            errors.append(f'Editable internal dependency is not portable: {name}')
    return errors


def _check_response(client: object, path: str, *, status: int = 200) -> object:
    response = client.get(path)
    if response.status_code != status:
        raise AssertionError(f'Unexpected HTTP status for {path}: {response.status_code}')
    return response


# La aplicación real se compone y se ejercitan rutas, callback Dash y assets por HTTP.
def probe(*, profile: str, application: Path, portable: bool) -> dict[str, object]:
    package_name = 'application-starter' if profile == 'generic' else 'ada-application-starter'
    metadata.version(package_name)
    from atlanticus.web.application import create_web_application
    from dash import page_registry

    if profile == 'generic':
        from application.composition import create_application_definition

        runtime = create_web_application(create_application_definition())
    else:
        from ada.web.application.generic.bootstrap import create_operational_application_runtime
        from ada.web.application.generic.settings import AdaGenericSettings
        from application.composition import create_composition

        settings = AdaGenericSettings.from_mapping({
            'ATLANTICUS_ENVIRONMENT': 'local',
            'ADA_TOOL_NAMESPACE': 'qualification',
            'ADA_TOOL_SOURCE_PROVIDER': 'local',
            'ADA_TOOL_PROJECTION_PROVIDER': 'local',
            'ADA_TOOL_LOCAL_BASE_ROOT': os.environ['STARTER_QUALIFICATION_LOCAL_ROOT'],
        })
        runtime = create_operational_application_runtime(
            settings=settings, composition_factory=create_composition,
        )
    checks: list[str] = []
    client = runtime.server.test_client()
    live = _check_response(client, '/health/live').get_json()
    if live.get('status') != 'alive':
        raise AssertionError('Health liveness response is invalid')
    checks.append('health.live')
    ready = client.get('/health/ready')
    if ready.status_code not in (200, 503) or ready.get_json().get('status') not in (
        'ready', 'not_ready',
    ):
        raise AssertionError('Health readiness response is invalid')
    checks.append('health.ready.diagnostic')
    _check_response(client, '/')
    checks.append('home.http')
    _check_response(client, '/example')
    checks.append('example.http')
    layout = _check_response(client, '/_dash-layout').get_json()
    expected_root = 'application-content' if profile == 'generic' else 'ada-generic-application'
    if expected_root not in json.dumps(layout):
        raise AssertionError('Dash application layout is missing the expected root')
    checks.append('dash.layout')
    expected_page = 'application.modules.example.pages.overview'
    if expected_page not in runtime.page_modules or expected_page not in page_registry:
        raise AssertionError('Example module page is not registered')
    checks.append('module.page.registration')
    dependencies = _check_response(client, '/_dash-dependencies').get_json()
    if not isinstance(dependencies, list) or not any(
        'starter-example-result.children' in str(entry.get('output'))
        for entry in dependencies
    ):
        raise AssertionError('Example callback is missing from Dash dependencies')
    checks.append('module.callback.registration')
    response = client.post('/_dash-update-component', json={
        'output': 'starter-example-result.children',
        'outputs': {'id': 'starter-example-result', 'property': 'children'},
        'inputs': [{'id': 'starter-example-button', 'property': 'n_clicks', 'value': 3}],
        'state': [],
        'changedPropIds': ['starter-example-button.n_clicks'],
    })
    if response.status_code != 200 or 'Activations: 3' not in response.get_data(as_text=True):
        raise AssertionError('Example callback did not return the expected result')
    checks.append('module.callback.http')
    css_entries = [entry for entry in runtime.assets.css_entries
                   if 'starter_example' in entry and entry.endswith('.css')]
    if len(css_entries) != 1:
        raise AssertionError('Expected one published example module stylesheet')
    css_response = _check_response(client, '/assets/' + css_entries[0])
    if b'#starter-example-page' not in css_response.data:
        raise AssertionError('Published example stylesheet contents are invalid')
    checks.append('module.assets.http')
    errors = _verify_dependencies(portable)
    if errors:
        return {'status': 'FAIL', 'checks': checks, 'errors': errors}
    return {'status': 'PASS', 'checks': checks, 'python': sys.version.split()[0],
            'readiness': ready.get_json()['status']}


# El proceso auxiliar expone un resultado estructurado al orquestador.
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', choices=('generic', 'ada'), required=True)
    parser.add_argument('--application', type=Path, required=True)
    parser.add_argument('--portable', action='store_true')
    args = parser.parse_args()
    try:
        outcome = probe(profile=args.profile, application=args.application,
                        portable=args.portable)
    except Exception as error:
        outcome = {'status': 'FAIL', 'error_type': type(error).__name__,
                   'error': str(error)}
    print('STARTER_QUALIFICATION_RESULT:' + json.dumps(outcome, ensure_ascii=False))
    raise SystemExit(0 if outcome['status'] == 'PASS' else 1)


if __name__ == '__main__':
    main()
