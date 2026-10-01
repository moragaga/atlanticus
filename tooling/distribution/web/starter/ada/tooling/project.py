from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_REPOSITORY_TOOLING = (
    Path(__file__).resolve().parents[3] / 'ada/project-tooling/src/ada_project_tooling/cli.py'
)
_TOOLING_PACKAGE = 'ada-project-tooling'
_TOOLING_MEMBER = 'ada_project_tooling/cli.py'


def _wheel_source() -> bytes:
    manifest = json.loads((_PROJECT_ROOT / 'wheelhouse/manifest.json').read_text(encoding='utf-8'))
    records = [
        record for record in manifest.get('packages', ())
        if record.get('name') == _TOOLING_PACKAGE
    ]
    if len(records) != 1:
        raise RuntimeError('ADA project tooling package is missing or ambiguous')
    record = records[0]
    filename = record.get('filename')
    digest = record.get('sha256')
    if not isinstance(filename, str) or Path(filename).name != filename:
        raise RuntimeError('ADA project tooling wheel identity is invalid')
    wheel = _PROJECT_ROOT / 'wheelhouse' / filename
    if not wheel.is_file() or hashlib.sha256(wheel.read_bytes()).hexdigest() != digest:
        raise RuntimeError('ADA project tooling wheel integrity failed')
    try:
        with zipfile.ZipFile(wheel) as archive:
            return archive.read(_TOOLING_MEMBER)
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        raise RuntimeError('ADA project tooling wheel cannot be loaded') from error


def _implementation_source() -> bytes:
    if _REPOSITORY_TOOLING.is_file():
        return _REPOSITORY_TOOLING.read_bytes()
    return _wheel_source()


exec(compile(_implementation_source(), _TOOLING_MEMBER, 'exec'), globals())
_project_main = globals()['main']


def _root() -> Path:
    return _PROJECT_ROOT


def main(argv: list[str] | None = None) -> None:
    _project_main(argv, root=_PROJECT_ROOT)


if __name__ == '__main__':
    main()
