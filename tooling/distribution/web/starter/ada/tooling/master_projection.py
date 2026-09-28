from __future__ import annotations

import subprocess
import sys

from project import ProjectError, _check_environment, _locked, _python, _root


def main(argv: list[str] | None = None) -> int:
    root = _root()
    try:
        _check_environment(root)
        _locked(root)
        interpreter = _python(root)
        if not interpreter.is_file():
            raise ProjectError('Initialize and sync the distributed ADA project first')
    except (OSError, ProjectError, ValueError) as error:
        print(f'BLOCKED: {error}', file=sys.stderr)
        return 2
    try:
        result = subprocess.run(
            [str(interpreter), '-m', 'application.master_projection.material',
             *(argv if argv is not None else sys.argv[1:])],
            cwd=root, check=False,
        )
    except OSError:
        print('BLOCKED: Master Projection material tooling is unavailable', file=sys.stderr)
        return 2
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
