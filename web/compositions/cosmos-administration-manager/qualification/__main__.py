from __future__ import annotations

import argparse
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from atlanticus.connectivity.cosmos import CosmosClient, CosmosSettings
from atlanticus.web.cosmos_administration import CosmosAdministrationService
from qualification.runtime import (
    DEMO_PASSWORD,
    DEMO_USER,
    build_qualification_runtime,
)


def main() -> None:
    parser = argparse.ArgumentParser(description='Local-only Cosmos ROOT Manager qualification')
    parser.add_argument('--port', type=int, default=8050)
    parser.add_argument('--connection-name', required=True)
    parser.add_argument('--endpoint', required=True)
    parser.add_argument('--database', required=True)
    parser.add_argument('--allow-insecure-http', action='store_true')
    parser.add_argument('--local-user', choices=('jane', 'john'))
    options = parser.parse_args()
    if not 1024 <= options.port <= 65535:
        parser.error('Port must be between 1024 and 65535')
    if os.environ.get('ATLANTICUS_ENVIRONMENT', 'local').strip().lower() != 'local':
        parser.error('Cosmos qualification cannot run outside local environment')
    key = os.environ.get('ATLANTICUS_COSMOS_QUALIFICATION_KEY')
    if not key:
        parser.error('ATLANTICUS_COSMOS_QUALIFICATION_KEY is required')
    os.environ['ATLANTICUS_ENVIRONMENT'] = 'local'
    client = CosmosClient(
        settings=CosmosSettings(
            endpoint=options.endpoint,
            key=key,
            database_name=options.database,
            allow_insecure_http=options.allow_insecure_http,
        )
    )
    try:
        administration = CosmosAdministrationService(connections={options.connection_name: client})
        with TemporaryDirectory(prefix='atlanticus-cosmos-root-qualification-') as path:
            runtime = build_qualification_runtime(
                directory=Path(path),
                administration=administration,
                local_user=options.local_user,
            )
            print('Local Cosmos ROOT qualification (not for production)', flush=True)
            print(f'Login: http://127.0.0.1:{options.port}/manager-root/login', flush=True)
            print(f'Manager: http://127.0.0.1:{options.port}/manager', flush=True)
            print(
                f'Cosmos: http://127.0.0.1:{options.port}/manager/cosmos-administration',
                flush=True,
            )
            if options.local_user is None:
                print(f'Demo user: {DEMO_USER}', flush=True)
                print(f'Demo password: {DEMO_PASSWORD}', flush=True)
            else:
                print(f'Local ROOT identity: {options.local_user}', flush=True)
                print('No separate ROOT login is required for this local identity.', flush=True)
            runtime.web.server.run(
                host='127.0.0.1',
                port=options.port,
                debug=False,
                use_reloader=False,
                threaded=False,
            )
    finally:
        client.close()


if __name__ == '__main__':
    main()
