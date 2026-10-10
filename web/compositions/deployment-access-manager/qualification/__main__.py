from __future__ import annotations

import argparse
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from qualification.runtime import (
    DEMO_LOCK_SECONDS,
    DEMO_MAX_FAILURES,
    DEMO_PASSWORD,
    DEMO_USER,
    build_qualification_runtime,
)


def main() -> None:
    parser = argparse.ArgumentParser(description='Local-only Atlanticus ROOT visual qualification')
    parser.add_argument('--port', type=int, default=8050)
    options = parser.parse_args()
    if not 1024 <= options.port <= 65535:
        parser.error('Port must be between 1024 and 65535')
    if os.environ.get('ATLANTICUS_ENVIRONMENT', 'local').strip().lower() != 'local':
        parser.error('ROOT visual qualification cannot run outside local environment')
    os.environ['ATLANTICUS_ENVIRONMENT'] = 'local'

    with TemporaryDirectory(prefix='atlanticus-root-qualification-') as path:
        runtime = build_qualification_runtime(directory=Path(path))
        print('Local ROOT qualification (not for production)', flush=True)
        print(f'Login: http://127.0.0.1:{options.port}/manager-root/login', flush=True)
        print(f'Manager: http://127.0.0.1:{options.port}/manager', flush=True)
        print(f'Demo user: {DEMO_USER}', flush=True)
        print(f'Demo password: {DEMO_PASSWORD}', flush=True)
        print(
            f'Lockout: {DEMO_MAX_FAILURES} incorrect passwords; '
            f'next attempt returns HTTP 429 for {DEMO_LOCK_SECONDS} seconds',
            flush=True,
        )
        print('Stop with Ctrl+C. Demo material is removed at exit.', flush=True)
        runtime.web.server.run(
            host='127.0.0.1',
            port=options.port,
            debug=False,
            use_reloader=False,
            threaded=False,
        )


if __name__ == '__main__':
    main()
