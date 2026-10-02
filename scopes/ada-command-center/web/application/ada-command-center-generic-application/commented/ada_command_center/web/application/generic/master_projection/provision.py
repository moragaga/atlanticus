from __future__ import annotations

# Espejo pedagógico: el material se genera manualmente y se persiste según el provider configurado.
import argparse
import getpass
import json
import sys
import tempfile
from pathlib import Path

from ada_command_center.web.application.configuration_manager.catalog_configuration import (
    STORAGE_CONTAINER_VARIABLE,
    ManagerConfigurationReader,
    catalog_storage_settings,
)
from ada_command_center.web.application.generic.master_projection.location import (
    COMMAND_CENTER_MASTER_APPLICATION_NAMESPACE,
    COMMAND_CENTER_MASTER_BLOB_NAME,
    master_projection_local_path,
)
from atlanticus.connectivity.storage import (
    StorageClient,
    StorageConflictError,
    StorageError,
)
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


def _generate_local(
    reader: ManagerConfigurationReader,
    *,
    service_user: str,
    password: str,
    base_root: Path | None = None,
) -> dict[str, str]:
    root = (base_root if base_root is not None else Path.cwd() / '.runtime').expanduser()
    target = master_projection_local_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    identity = generate_master_material(
        target,
        service_user=service_user,
        password=password,
        application_namespace=COMMAND_CENTER_MASTER_APPLICATION_NAMESPACE,
        environment=reader.environment.value,
    )
    return {
        'status': 'GENERATED',
        'material_id': identity.material_id,
        'persistence': 'local',
        'location': str(target),
    }


def _generate_durable(
    reader: ManagerConfigurationReader,
    *,
    service_user: str,
    password: str,
) -> dict[str, str]:
    values = reader.storage()
    container_name = values[STORAGE_CONTAINER_VARIABLE]
    with tempfile.TemporaryDirectory(prefix='command-center-master-projection-') as directory:
        target = Path(directory) / 'material.zip'
        identity = generate_master_material(
            target,
            service_user=service_user,
            password=password,
            application_namespace=COMMAND_CENTER_MASTER_APPLICATION_NAMESPACE,
            environment=reader.environment.value,
        )
        try:
            with StorageClient(settings=catalog_storage_settings(values)) as storage:
                storage.upload(
                    container_name=container_name,
                    blob_name=COMMAND_CENTER_MASTER_BLOB_NAME,
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
        'persistence': 'durable',
        'location': f'blob://{container_name}/{COMMAND_CENTER_MASTER_BLOB_NAME}',
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Provision ADA Command Center Master Projection access material'
    )
    parser.add_argument('action', choices=('generate',))
    parser.add_argument('--user', required=True)
    options = parser.parse_args(argv)
    try:
        reader = ManagerConfigurationReader(root=Path.cwd())
        password = _password()
        result = (
            _generate_local(reader, service_user=options.user, password=password)
            if reader.manager_provider == 'local'
            else _generate_durable(reader, service_user=options.user, password=password)
        )
    except (MasterMaterialError, OSError, ValueError) as error:
        print(f'BLOCKED: {error}', file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
