from __future__ import annotations

import hashlib
import json
import re
import tomllib
from pathlib import Path


class NativeUvSourceError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_native_uv_sources(project: Path, wheelhouse: Path, packages: list[dict]) -> None:
    text = project.read_text(encoding='utf-8')
    parsed = tomllib.loads(text)
    if parsed.get('project', {}).get('name') != 'ada-integrated-operations-application':
        raise NativeUvSourceError('Expected the Integrated Operations project')
    if re.search(r'(?m)^\[tool\.uv(?:\.|\])', text):
        raise NativeUvSourceError('Existing uv settings cannot be replaced')
    if not isinstance(packages, list) or not packages:
        raise NativeUvSourceError('Internal wheel records are missing')

    selected: list[tuple[str, str]] = []
    seen: set[str] = set()
    for record in packages:
        if not isinstance(record, dict):
            raise NativeUvSourceError('Invalid internal wheel record')
        name, filename, digest = (record.get(key) for key in ('name', 'filename', 'sha256'))
        if not isinstance(name, str) or not re.fullmatch(r'[a-z][a-z0-9-]*', name):
            raise NativeUvSourceError('Invalid internal wheel name')
        if not isinstance(filename, str) or Path(filename).name != filename or not filename.endswith('-py3-none-any.whl'):
            raise NativeUvSourceError(f'Invalid portable wheel: {name}')
        if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise NativeUvSourceError(f'Invalid wheel digest: {name}')
        if name in seen:
            raise NativeUvSourceError(f'Duplicate internal wheel: {name}')
        seen.add(name)
        wheel = wheelhouse / filename
        if not wheel.is_file() or wheel.is_symlink() or _sha256(wheel) != digest:
            raise NativeUvSourceError(f'Internal wheel integrity failed: {filename}')
        if name != 'ada-project-tooling':
            selected.append((name, filename))

    if 'ada-generic-application' not in dict(selected):
        raise NativeUvSourceError('ADA Generic internal wheel is missing')

    lines = [text.rstrip(), '', '[tool.uv.sources]']
    for name, filename in sorted(selected):
        lines.append(
            f'{json.dumps(name)} = {{ path = {json.dumps("wheelhouse/" + filename)} }}'
        )
    lines.append('')
    generated = '\n'.join(lines)
    tomllib.loads(generated)
    project.write_text(generated, encoding='utf-8')
