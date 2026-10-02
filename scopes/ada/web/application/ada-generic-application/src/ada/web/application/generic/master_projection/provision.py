from __future__ import annotations

import argparse
import getpass
import json
import sys
import tempfile
from pathlib import Path

from ada.web.application.generic.settings import AdaGenericSettings, AdaPersistenceMode
from atlanticus.connectivity.storage import StorageClient, StorageConflictError, StorageError
from atlanticus.web.master_projection.material import (
    MasterMaterialError,
    generate_master_material,
)


def _password() -> str:
    if not sys.stdin.isatty():
        raise MasterMaterialError(
            'Master Projection material generation requires an interactive terminal'
        )
    password = getpass.getpass('Master Projection password: ')
    repeated = getpass.getpass('Repeat Master Projection password: ')
    if password != repeated:
        raise MasterMaterialError('Master Projection passwords do not match')
    return password


def _generate_local(settings: AdaGenericSettings, *, service_user: str, password: str) -> dict:
    target = settings.master_projection_local_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    identity = generate_master_material(
        target,
        service_user=service_user,
        password=password,
        application_namespace=settings.application_namespace,
        environment=settings.environment.value,
    )
    return {
        'status': 'GENERATED',
        'material_id': identity.material_id,
        'persistence': settings.persistence_mode.value,
        'location': str(target),
    }


def _generate_durable(settings: AdaGenericSettings, *, service_user: str, password: str) -> dict:
    storage_settings = settings.storage_settings()
    container_name = settings.storage_container_name
    if storage_settings is None or container_name is None:
        raise MasterMaterialError('Durable Master Projection storage is not configured')
    blob_name = settings.master_projection_blob_name()
    with tempfile.TemporaryDirectory(prefix='atlanticus-master-projection-') as directory:
        target = Path(directory) / 'material.zip'
        identity = generate_master_material(
            target,
            service_user=service_user,
            password=password,
            application_namespace=settings.application_namespace,
            environment=settings.environment.value,
        )
        try:
            with StorageClient(settings=storage_settings) as storage:
                storage.upload(
                    container_name=container_name,
                    blob_name=blob_name,
                    data=target.read_bytes(),
                    overwrite=False,
                    content_type='application/zip',
                )
        except StorageConflictError as error:
            raise MasterMaterialError('Master Projection material already exists') from error
        except StorageError as error:
            raise MasterMaterialError('Master Projection material could not be stored') from error
    return {
        'status': 'GENERATED',
        'material_id': identity.material_id,
        'persistence': settings.persistence_mode.value,
        'location': f'blob://{container_name}/{blob_name}',
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Provision Master Projection access material')
    parser.add_argument('action', choices=('generate',))
    parser.add_argument('--user', required=True)
    options = parser.parse_args(argv)
    try:
        settings = AdaGenericSettings()
        password = _password()
        if settings.persistence_mode is AdaPersistenceMode.LOCAL:
            result = _generate_local(settings, service_user=options.user, password=password)
        else:
            result = _generate_durable(settings, service_user=options.user, password=password)
    except (MasterMaterialError, OSError, ValueError) as error:
        print(f'BLOCKED: {error}', file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
