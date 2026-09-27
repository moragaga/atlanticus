from __future__ import annotations

# Bootstrap exclusivo de los emuladores locales; jamás crea infraestructura de Azure.

import socket
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import urlopen

from azure.core.exceptions import ResourceExistsError
from azure.storage.blob import BlobServiceClient

from ada.web.application.generic.manager_deployment import (
    open_durable_manager,
    prepare_durable_manager_resources,
)
from ada.web.application.generic.settings import AdaGenericSettings
from atlanticus.web.configuration import WebEnvironment

_COSMOS_READY = 'http://cosmos-emulator:8080/ready'
_WAIT_SECONDS = 180


# Limitar efectos a los dos servicios y puertos DNS conocidos del Compose.
def _is_emulator_configuration(settings: AdaGenericSettings) -> bool:
    endpoint = urlsplit(settings.tool_projection_cosmos_endpoint or '')
    connection = settings.tool_source_blob_connection_string
    if connection is None:
        return False
    parts = dict(
        piece.split('=', 1)
        for piece in connection.get_secret_value().split(';')
        if '=' in piece
    )
    blob = urlsplit(parts.get('BlobEndpoint', ''))
    return (
        settings.environment.is_local
        and settings.tool_source_provider.value == 'blob'
        and settings.tool_projection_provider.value == 'cosmos'
        and endpoint.scheme == 'http'
        and endpoint.hostname == 'cosmos-emulator'
        and endpoint.port == 8081
        and blob.scheme == 'http'
        and blob.hostname == 'azurite'
        and blob.port == 10000
        and blob.path.rstrip('/') == '/devstoreaccount1'
        and settings.tool_source_blob_container_name is not None
    )


# Esperar readiness de Cosmos y conexión Blob; no asumir que container_started es ready.
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
        except (HTTPError, URLError, TimeoutError, OSError):
            pass
        time.sleep(2)
    raise RuntimeError('Local Cosmos or Azurite was not ready before timeout')


# Crear exclusivamente el contenedor Blob local faltante y asegurar el plan Cosmos actual.
def prepare_local_resources() -> tuple[str, ...]:
    settings = AdaGenericSettings()
    if not _is_emulator_configuration(settings):
        raise RuntimeError('Local resource preparation requires the isolated Compose emulators')
    _wait_for_emulators()
    credential = settings.tool_source_blob_connection_string
    container = settings.tool_source_blob_container_name
    if credential is None or container is None:
        raise RuntimeError('Local Blob settings are incomplete')
    with BlobServiceClient.from_connection_string(credential.get_secret_value()) as client:
        try:
            client.create_container(container)
        except ResourceExistsError:
            pass
    with open_durable_manager(settings) as manager:
        return prepare_durable_manager_resources(
            manager,
            action='ensure-local',
            environment=WebEnvironment.LOCAL,
        )


def main() -> None:
    containers = prepare_local_resources()
    print(f'Local ADA Manager resources ready: {len(containers)} Cosmos containers')


if __name__ == '__main__':
    main()
