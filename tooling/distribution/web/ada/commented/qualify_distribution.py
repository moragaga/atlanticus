from __future__ import annotations

# Espejo pedagógico en español del código productivo.

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

from build_distribution import _validate_hashed_requirements


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


# Verifica origen, hashes y ruedas antes de indicar que el build Docker puede comenzar.
def qualify_ada_distribution(application: Path) -> dict:
    application = application.expanduser().resolve()
    try:
        starter = json.loads((application / 'manifest.json').read_text(encoding='utf-8'))
        if starter.get('profile') != 'ada':
            raise ValueError('Expected an ADA Starter')
        entries = starter.get('files')
        if not isinstance(entries, dict) or not entries:
            raise ValueError('ADA Starter source manifest is incomplete')
        for name, digest in entries.items():
            relative = Path(name)
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('ADA Starter source manifest contains an unsafe path')
            target = application / relative
            if not target.is_file() or _sha256(target) != digest:
                raise ValueError(f'ADA Starter source integrity failed: {name}')
        verifier = application / 'docker/verify_delivery.py'
        spec = importlib.util.spec_from_file_location('ada_image_delivery_verifier', verifier)
        if spec is None or spec.loader is None:
            raise ValueError('ADA distribution verifier is unavailable')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        count = module.verify_delivery(application)
        for name in ('external-runtime.txt', 'host-runtime.txt', 'starter-build.txt'):
            _validate_hashed_requirements(application / 'requirements' / name)
    except (OSError, ValueError, RuntimeError) as error:
        return {'status': 'BLOCKED', 'profile': 'ada', 'error': str(error)}
    return {
        'status': 'PRECHECK_PASS',
        'profile': 'ada',
        'internal_wheels': count,
        'image_build': 'UNVERIFIED',
        'runtime': 'UNVERIFIED',
    }


# El precheck no implica que Docker o el runtime hayan sido validados.
def main() -> None:
    parser = argparse.ArgumentParser(description='Preflight for ADA distribution Docker image')
    parser.add_argument('--application', required=True, type=Path)
    options = parser.parse_args()
    result = qualify_ada_distribution(options.application)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    raise SystemExit(0 if result['status'] == 'PRECHECK_PASS' else 2)


if __name__ == '__main__':
    main()
