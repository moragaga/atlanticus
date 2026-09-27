from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from packaging.tags import Tag
from packaging.utils import canonicalize_name, parse_wheel_filename

_SHARED_BUILDER = Path(__file__).resolve().parents[1] / 'build_wheelhouse.py'
_spec = importlib.util.spec_from_file_location('atlanticus_shared_web_wheels', _SHARED_BUILDER)
if _spec is None or _spec.loader is None:
    raise RuntimeError('Shared Web wheel builder is unavailable')
wheels = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wheels)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
HOST_REQUIREMENTS = ('gunicorn==23.0.0',)
_REQUIREMENT = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]*(?:\[[A-Za-z0-9_,.-]+\])?==[^\s;\\]+(?:\s*;\s*[^\\]+)?$')
_HASH = re.compile(r'--hash=sha256:[a-f0-9]{64}')


class AdaDistributionError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _run(command: list[str], *, cwd: Path) -> None:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        lines = result.stderr.strip().splitlines()
        safe = [
            '[diagnostic redacted]' if re.search(
                r'(?i)(://[^/\s]+@|bearer |token[=:]|password[=:]|secret[=:])', line
            ) else line
            for line in lines
        ]
        diagnostic = '\n'.join(safe)[-2500:]
        detail = f'\n{diagnostic}' if diagnostic else ''
        raise AdaDistributionError(
            f'ADA distribution command failed (exit {result.returncode}): {command[1]}{detail}'
        )


def _validate_hashed_requirements(path: Path) -> None:
    requirements = 0
    hashed = False
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('--hash='):
            if requirements == 0 or not _HASH.fullmatch(line.rstrip('\\').strip()):
                raise AdaDistributionError(f'Invalid SHA256 requirement in {path.name}')
            hashed = True
            continue
        if requirements and not hashed:
            raise AdaDistributionError(f'Unhashed distribution requirement in {path.name}')
        if not _REQUIREMENT.fullmatch(line.rstrip('\\').strip()):
            raise AdaDistributionError(f'Unpinned or unhashed distribution requirement in {path.name}')
        requirements += 1
        hashed = False
    if not requirements or not hashed:
        raise AdaDistributionError(f'Empty or unhashed distribution requirement in {path.name}')


def _write_external_requirements(*, uv: str, project: Path, staging: Path) -> tuple[Path, Path]:
    output = staging / 'external-runtime.txt'
    constraints = staging / 'constraints.txt'
    common = [uv, 'export', '--project', str(project), '--locked', '--no-dev',
              '--no-default-groups', '--no-emit-local', '--format', 'requirements.txt']
    _run([*common, '--output-file', str(output)], cwd=project)
    _run([*common, '--no-hashes', '--output-file', str(constraints)], cwd=project)
    _validate_hashed_requirements(output)
    return output, constraints


def _write_host_requirements(*, uv: str, staging: Path, constraints: Path) -> Path:
    input_file = staging / 'host.in'
    output = staging / 'host-runtime.txt'
    input_file.write_text('\n'.join(HOST_REQUIREMENTS) + '\n', encoding='utf-8')
    _run([
        uv, 'pip', 'compile', str(input_file), '--no-sources',
        '--python-version', wheels.PYTHON_VERSION, '--only-binary', ':all:',
        '--generate-hashes', '--constraints', str(constraints),
        '--output-file', str(output),
    ], cwd=staging)
    _validate_hashed_requirements(output)
    return output


def _write_starter_build_requirements(*, uv: str, staging: Path,
                                      build_requirements: list[str]) -> Path:
    input_file = staging / 'starter-build.in'
    output = staging / 'starter-build.txt'
    if not build_requirements:
        raise AdaDistributionError('ADA Starter has no pinned build requirements')
    input_file.write_text('\n'.join(build_requirements) + '\n', encoding='utf-8')
    _run([
        uv, 'pip', 'compile', str(input_file), '--no-sources',
        '--python-version', wheels.PYTHON_VERSION, '--only-binary', ':all:',
        '--generate-hashes', '--output-file', str(output),
    ], cwd=staging)
    _validate_hashed_requirements(output)
    return output


def _build_internal(*, uv: str, project: Path, target: Path, staging: Path) -> list[dict]:
    lock_path = staging / 'pylock.runtime.toml'
    _run([
        uv, 'export', '--project', str(project), '--locked', '--no-dev',
        '--no-default-groups', '--format', 'pylock.toml',
        '--output-file', str(lock_path),
    ], cwd=project)
    exported = wheels._read_toml(lock_path)
    if exported.get('lock-version') != '1.0' or not isinstance(exported.get('packages'), list):
        raise AdaDistributionError('ADA runtime export has an unsupported pylock format')
    local = [entry for entry in wheels._active_packages(exported) if 'directory' in entry]
    if not local or not any(canonicalize_name(entry['name']) == 'ada-generic-application' for entry in local):
        raise AdaDistributionError('ADA runtime lock does not include its internal application')
    records = []
    seen = set()
    for entry in local:
        source = wheels._local_directory(entry, project, REPOSITORY_ROOT)
        metadata = wheels._read_toml(source / 'pyproject.toml')['project']
        name, version = metadata['name'], str(metadata['version'])
        identity = canonicalize_name(name)
        if identity in seen:
            raise AdaDistributionError(f'Duplicate internal package in runtime lock: {identity}')
        seen.add(identity)
        filename = wheels._build_internal(uv, source, target, name, version)
        _, _, _, tags = parse_wheel_filename(filename)
        if Tag('py3', 'none', 'any') not in tags:
            raise AdaDistributionError(f'Internal wheel is not portable to the image: {filename}')
        records.append({
            'name': identity,
            'version': version,
            'filename': filename,
            'sha256': _sha256(target / filename),
            'source': source.relative_to(REPOSITORY_ROOT).as_posix(),
        })
    return sorted(records, key=lambda item: item['name'])


def build_ada_distribution(*, application: Path, uv: str) -> dict:
    wheels._require_python()
    application = application.expanduser().resolve()
    starter = wheels._validate_starter(application, 'ada')
    if (application / 'wheelhouse').exists() or (application / 'requirements').exists():
        raise AdaDistributionError('Regenerate the ADA Starter before building its distribution')
    project = REPOSITORY_ROOT / 'scopes/ada/web/application/ada-generic-application'
    with tempfile.TemporaryDirectory(prefix='.ada-delivery-', dir=application) as temporary:
        staging = Path(temporary)
        target = staging / 'wheelhouse'
        target.mkdir()
        external, constraints = _write_external_requirements(
            uv=uv, project=project, staging=staging
        )
        host = _write_host_requirements(uv=uv, staging=staging, constraints=constraints)
        starter_build = _write_starter_build_requirements(
            uv=uv, staging=staging,
            build_requirements=wheels._build_requirements([application]),
        )
        records = _build_internal(uv=uv, project=project, target=target, staging=staging)
        requirements = staging / 'requirements'
        requirements.mkdir()
        for source in (external, host, starter_build):
            shutil.copyfile(source, requirements / source.name)
        revision = subprocess.run(
            ['git', 'rev-parse', 'HEAD'], cwd=REPOSITORY_ROOT,
            text=True, capture_output=True, check=True,
        ).stdout.strip()
        metadata = {
            'schema_version': 2,
            'strategy': 'internal-wheels-external-image-build',
            'python': wheels.PYTHON_VERSION,
            'profile': 'ada',
            'source_git_head': revision,
            'qualification': 'UNVERIFIED',
            'runtime_lock_sha256': _sha256(project / 'uv.lock'),
            'requirements': {
                item.name: _sha256(item) for item in sorted(requirements.iterdir())
            },
            'packages': records,
        }
        (target / 'manifest.json').write_text(
            json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
            encoding='utf-8',
        )
        target.rename(application / 'wheelhouse')
        try:
            requirements.rename(application / 'requirements')
            starter['wheelhouse_included'] = True
            starter['delivery_strategy'] = metadata['strategy']
            staged_manifest = staging / 'starter-manifest.json'
            staged_manifest.write_text(
                json.dumps(starter, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
                encoding='utf-8',
            )
            staged_manifest.replace(application / 'manifest.json')
        except OSError:
            shutil.rmtree(application / 'wheelhouse')
            if (application / 'requirements').exists():
                shutil.rmtree(application / 'requirements')
            raise
    return {
        'status': 'BUILT_UNQUALIFIED',
        'profile': 'ada',
        'delivery_strategy': metadata['strategy'],
        'internal_wheels': len(records),
        'source_git_head': revision,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Build an ADA image distribution')
    parser.add_argument('--application', type=Path, default=REPOSITORY_ROOT / 'distribution/ada-web-starter')
    options = parser.parse_args()
    uv = shutil.which('uv')
    if uv is None:
        raise SystemExit('uv executable is required')
    try:
        result = build_ada_distribution(application=options.application, uv=uv)
    except (AdaDistributionError, OSError, subprocess.CalledProcessError, wheels.WheelhouseBuildError) as error:
        print(json.dumps({'status': 'BLOCKED', 'error': str(error)}, ensure_ascii=False, indent=2))
        raise SystemExit(2) from error
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
