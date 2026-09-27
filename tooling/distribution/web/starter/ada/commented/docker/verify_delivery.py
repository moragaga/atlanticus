from __future__ import annotations

# Espejo pedagógico: mismo código ejecutable con comentarios en español.

import hashlib
import json
import platform
import sys
from pathlib import Path


# Fallar antes de la instalación si hay divergencia en la distribución.
class DeliveryValidationError(ValueError):
    pass


# La comprobación de integridad lee cada archivo por bloques.
def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


# El image build verifica exactamente el wheelhouse propio y los dos requisitos externos.
def verify_delivery(application: Path) -> int:
    starter = json.loads((application / 'manifest.json').read_text(encoding='utf-8'))
    wheelhouse = application / 'wheelhouse'
    manifest = json.loads((wheelhouse / 'manifest.json').read_text(encoding='utf-8'))
    strategy = 'internal-wheels-external-image-build'
    if (starter.get('artifact_kind') != 'web-application-starter'
            or starter.get('profile') != 'ada'
            or starter.get('wheelhouse_included') is not True
            or starter.get('delivery_strategy') != strategy):
        raise DeliveryValidationError('ADA Starter manifest has an invalid delivery contract')
    if (manifest.get('schema_version') != 2 or manifest.get('strategy') != strategy
            or manifest.get('profile') != 'ada'
            or manifest.get('python') != platform.python_version()):
        raise DeliveryValidationError('ADA distribution contract or image Python differs')
    requirements = manifest.get('requirements')
    required = {'external-runtime.txt', 'host-runtime.txt', 'starter-build.txt'}
    if not isinstance(requirements, dict) or set(requirements) != required:
        raise DeliveryValidationError('ADA external requirements inventory is incomplete')
    for name, digest in requirements.items():
        path = application / 'requirements' / name
        if not path.is_file() or _sha256(path) != digest:
            raise DeliveryValidationError(f'ADA requirements integrity failed: {name}')
    packages = manifest.get('packages')
    if not isinstance(packages, list) or not packages:
        raise DeliveryValidationError('ADA internal wheel inventory is empty')
    expected: set[str] = set()
    for package in packages:
        if not isinstance(package, dict):
            raise DeliveryValidationError('ADA internal wheel record is invalid')
        name, digest = package.get('filename'), package.get('sha256')
        if (not isinstance(name, str) or Path(name).name != name
                or not name.endswith('.whl') or name in expected
                or not isinstance(digest, str) or len(digest) != 64):
            raise DeliveryValidationError('ADA internal wheel identity is invalid')
        expected.add(name)
        path = wheelhouse / name
        if not path.is_file() or _sha256(path) != digest:
            raise DeliveryValidationError(f'ADA internal wheel integrity failed: {name}')
    if {path.name for path in wheelhouse.glob('*.whl')} != expected:
        raise DeliveryValidationError('ADA internal wheel inventory differs from its manifest')
    return len(packages)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: verify_delivery.py <application-root>')
    try:
        verify_delivery(Path(sys.argv[1]))
    except (DeliveryValidationError, OSError, ValueError) as error:
        raise SystemExit(str(error)) from error
