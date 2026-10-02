from __future__ import annotations

import json
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import urlopen

from ada.web.application.generic.manager_deployment import (
    open_durable_manager,
    prepare_durable_manager_resources,
)
from ada.web.application.generic.settings import AdaGenericSettings, AdaPersistenceMode
from atlanticus.web.configuration import WebEnvironment

_COSMOS_READY = 'http://cosmos-emulator:8080/ready'
_WAIT_SECONDS = 180


def _is_emulator_configuration(settings: AdaGenericSettings) -> bool:
    endpoint = urlsplit(settings.cosmos_endpoint or '')
    connection = settings.storage_connection_string
    if connection is None:
        return False
    parts = dict(
        piece.split('=', 1) for piece in connection.get_secret_value().split(';') if '=' in piece
    )
    blob = urlsplit(parts.get('BlobEndpoint', ''))
    return (
        settings.environment.is_local
        and settings.persistence_mode is AdaPersistenceMode.DURABLE
        and endpoint.scheme == 'http'
        and endpoint.hostname == 'cosmos-emulator'
        and endpoint.port == 8081
        and blob.scheme == 'http'
        and blob.hostname == 'azurite'
        and blob.port == 10000
        and blob.path.rstrip('/') == '/devstoreaccount1'
        and settings.storage_container_name is not None
    )


def _wait_for_emulators() -> None:
    deadline = time.monotonic() + _WAIT_SECONDS
    while time.monotonic() < deadline:
        try:
            with urlopen(_COSMOS_READY, timeout=3) as response:
                if response.status != 200:
                    time.sleep(2)
                    continue
            with socket.create_connection(('azurite', 10000), timeout=3):
                return
        except HTTPError, URLError, TimeoutError, OSError:
            pass
        time.sleep(2)
    raise RuntimeError('Local Cosmos or Azurite was not ready before timeout')


def prepare_local_resources(*, observe_failure=None):
    settings = AdaGenericSettings()
    if not _is_emulator_configuration(settings):
        raise RuntimeError('Local resource preparation requires the isolated Compose emulators')
    _wait_for_emulators()
    with open_durable_manager(settings) as manager:
        return prepare_durable_manager_resources(
            manager,
            action='prepare',
            environment=WebEnvironment.LOCAL,
            observe_failure=observe_failure,
        )


def main() -> None:
    from atlanticus.web.observability import configure_web_observability

    observer = configure_web_observability(application='ada-local-resources', json_output=True)

    def observe_failure(result):
        observer.error(
            'ada.resource.preparation.failed',
            'Resource preparation failed',
            resource_kind=result.kind,
            logical_id=result.logical_id,
            physical_name=result.physical_name,
            status=result.status.value,
            error_type=result.error_type,
        )

    try:
        report = prepare_local_resources(observe_failure=observe_failure)
    except Exception as error:
        observer.error(
            'ada.resource.preparation.unavailable',
            'Local resource preparation could not be started',
            error_type=type(error).__name__,
        )
        raise SystemExit(2) from error
    print(json.dumps(report.to_dict(), ensure_ascii=False))
    if report.status != 'COMPLETED':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
