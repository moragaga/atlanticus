# Punto de entrada del preview visual. Los argumentos permiten levantar dos Tools en puertos distintos.
from __future__ import annotations

import argparse

from atlanticus.web.application import run_web_application

from .runtime import create_preview_runtime


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Run the TS-012 Time Status visual preview.')
    parser.add_argument(
        '--tool',
        choices=('integrated_operations', 'process'),
        default='integrated_operations',
    )
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8050)
    return parser


def main() -> None:
    arguments = _parser().parse_args()
    run_web_application(
        create_preview_runtime(tool_key=arguments.tool),
        host=arguments.host,
        port=arguments.port,
    )


if __name__ == '__main__':
    main()
