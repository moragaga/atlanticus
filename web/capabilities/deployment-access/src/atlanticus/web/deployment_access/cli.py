from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from atlanticus.connectivity.storage import (
    StorageClient,
    StorageConnectionStringCredential,
    StorageError,
    StorageSasCredential,
    StorageSettings,
)
from atlanticus.web.deployment_access.material import DeploymentAccessMaterialError
from atlanticus.web.deployment_access.service import (
    DeploymentAccessService,
    DeploymentAccessVerificationError,
)
from atlanticus.web.deployment_access.storage import (
    BlobDeploymentAccessStorage,
    DeploymentAccessStorageError,
    LocalDeploymentAccessStorage,
)


def _credential(options: argparse.Namespace) -> StorageSettings:
    if options.connection_string_env and not (options.sas_account_url or options.sas_token_env):
        value = os.environ.get(options.connection_string_env)
        if not value:
            raise ValueError('Storage connection string environment variable is unavailable')
        return StorageSettings(credential=StorageConnectionStringCredential(value))
    if not options.connection_string_env and options.sas_account_url and options.sas_token_env:
        value = os.environ.get(options.sas_token_env)
        if not value:
            raise ValueError('Storage SAS token environment variable is unavailable')
        return StorageSettings(
            credential=StorageSasCredential(
                account_url=options.sas_account_url,
                sas_token=value,
                allow_insecure_http=options.allow_insecure_http,
            )
        )
    raise ValueError('Choose either connection string or account URL plus SAS token environment')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Bootstrap Atlanticus Manager deployment access')
    parser.add_argument('action', choices=('bootstrap',))
    parser.add_argument('--application', required=True)
    parser.add_argument('--environment', required=True)
    parser.add_argument('--user', required=True)
    parser.add_argument('--local-path', type=Path)
    parser.add_argument('--container')
    parser.add_argument('--blob')
    parser.add_argument('--connection-string-env')
    parser.add_argument('--sas-account-url')
    parser.add_argument('--sas-token-env')
    parser.add_argument('--allow-insecure-http', action='store_true')
    options = parser.parse_args(argv)
    if not sys.stdin.isatty():
        parser.error('Deployment access bootstrap requires an interactive terminal')
    if options.local_path is None and (not options.container or not options.blob):
        parser.error('Blob bootstrap requires --container and --blob')
    if options.local_path is not None and any(
        (
            options.container,
            options.blob,
            options.connection_string_env,
            options.sas_account_url,
            options.sas_token_env,
            options.allow_insecure_http,
        )
    ):
        parser.error('Local bootstrap cannot include Blob storage arguments')
    try:
        password = getpass.getpass('Deployment access password: ')
        repeated = getpass.getpass('Repeat deployment access password: ')
        if password != repeated:
            raise DeploymentAccessMaterialError('Deployment access passwords do not match')
        if options.local_path is not None:
            destination = options.local_path.expanduser().absolute()
            if destination.resolve().is_relative_to(Path.cwd().resolve()):
                raise ValueError('Deployment access material must be outside the project directory')
            service = DeploymentAccessService(
                storage=LocalDeploymentAccessStorage(destination),
                application_namespace=options.application,
                environment=options.environment,
            )
            identity = service.bootstrap_initial(service_user=options.user, password=password)
        else:
            with StorageClient(settings=_credential(options)) as client:
                service = DeploymentAccessService(
                    storage=BlobDeploymentAccessStorage(
                        client=client, container_name=options.container, blob_name=options.blob
                    ),
                    application_namespace=options.application,
                    environment=options.environment,
                )
                identity = service.bootstrap_initial(service_user=options.user, password=password)
    except (
        ValueError,
        OSError,
        DeploymentAccessMaterialError,
        DeploymentAccessStorageError,
        DeploymentAccessVerificationError,
        StorageError,
    ) as error:
        print(f'BLOCKED: {error}', file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                'status': 'CREATED',
                'material_id': identity.material_id,
                'application_namespace': identity.application_namespace,
                'environment': identity.environment,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
