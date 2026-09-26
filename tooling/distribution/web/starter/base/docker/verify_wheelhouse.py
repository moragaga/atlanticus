from __future__ import annotations

import hashlib
import json
import platform
import sys
from pathlib import Path


class WheelhouseValidationError(ValueError):
    pass


def verify_wheelhouse(application: Path) -> int:
    starter = json.loads((application / 'manifest.json').read_text(encoding='utf-8'))
    wheelhouse = application / 'wheelhouse'
    manifest = json.loads((wheelhouse / 'manifest.json').read_text(encoding='utf-8'))
    if starter.get('artifact_kind') != 'web-application-starter':
        raise WheelhouseValidationError('Starter manifest has an invalid artifact kind')
    if starter.get('wheelhouse_included') is not True:
        raise WheelhouseValidationError('Starter manifest does not declare its wheelhouse')
    if starter.get('profile') not in ('generic', 'ada'):
        raise WheelhouseValidationError('Starter profile is invalid')
    if manifest.get('schema_version') != 1 or manifest.get('profile') != starter['profile']:
        raise WheelhouseValidationError('Wheelhouse manifest profile or schema is invalid')
    if manifest.get('python') != platform.python_version():
        raise WheelhouseValidationError('Wheelhouse Python does not match the image')
    if manifest.get('platform') != sys.platform or manifest.get('machine') != platform.machine():
        raise WheelhouseValidationError('Wheelhouse platform does not match the image')
    packages = manifest.get('packages')
    if not isinstance(packages, list) or not packages:
        raise WheelhouseValidationError('Wheelhouse manifest has no packages')
    expected: set[str] = set()
    for package in packages:
        if not isinstance(package, dict):
            raise WheelhouseValidationError('Wheelhouse package record is invalid')
        name = package.get('filename')
        digest = package.get('sha256')
        if (
            not isinstance(name, str)
            or Path(name).name != name
            or not name.endswith('.whl')
            or not isinstance(digest, str)
            or len(digest) != 64
            or name in expected
        ):
            raise WheelhouseValidationError('Wheelhouse package identity is invalid')
        expected.add(name)
        path = wheelhouse / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise WheelhouseValidationError(f'Wheelhouse package integrity failed: {name}')
    actual = {path.name for path in wheelhouse.glob('*.whl') if path.is_file()}
    if actual != expected:
        raise WheelhouseValidationError('Wheelhouse files do not match their manifest')
    return len(packages)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: verify_wheelhouse.py <application-root>')
    try:
        verify_wheelhouse(Path(sys.argv[1]))
    except (WheelhouseValidationError, OSError, ValueError) as error:
        raise SystemExit(str(error)) from error
