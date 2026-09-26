from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PROBE = Path(__file__).with_name('probe_starter.py')


# Se comprueba el inventario publicado para detectar cambios accidentales en el Starter.
def verify_manifest(application: Path, profile: str) -> list[str]:
    manifest_path = application / 'manifest.json'
    if not manifest_path.is_file():
        return ['Generated application manifest is missing']
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    except (ValueError, OSError):
        return ['Generated application manifest is invalid']
    if manifest.get('artifact_kind') != 'web-application-starter':
        return ['Generated application has an unexpected artifact kind']
    if manifest.get('profile') != profile:
        return ['Generated application profile does not match qualification profile']
    entries = manifest.get('files')
    if not isinstance(entries, dict):
        return ['Generated application manifest has no file inventory']
    errors: list[str] = []
    recorded = set(entries)
    actual = {
        path.relative_to(application).as_posix()
        for path in application.rglob('*')
        if path.is_file() and path.name != 'manifest.json'
        and not {'__pycache__', '.pytest_cache', '.venv', '.runtime', '.git',
                 'build', 'dist', 'wheelhouse'}
        & set(path.relative_to(application).parts)
        and path.suffix != '.pyc'
        and not any(part.endswith('.egg-info') for part in path.relative_to(application).parts)
    }
    if actual != recorded:
        errors.append('Generated application file inventory differs from its manifest')
    for name, expected in entries.items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or not isinstance(expected, str):
            errors.append('Generated application manifest contains an invalid file entry')
            continue
        path = application / relative
        if not path.is_file():
            errors.append(f'Generated application file is missing: {name}')
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            errors.append(f'Generated application file integrity failed: {name}')
    return errors


def python_requirement(path: Path) -> str:
    data = tomllib.loads(path.read_text(encoding='utf-8'))
    return data['project']['requires-python']


# Se comparan los pines declarados por el Starter y la dependencia de entrada.
def python_conflicts(application: Path, profile: str) -> list[str]:
    constraints = [('starter', application / 'pyproject.toml')]
    if profile == 'generic':
        constraints.append(('atlanticus-web', REPOSITORY_ROOT / 'web/framework/core/pyproject.toml'))
    else:
        constraints.append((
            'ada-generic-application',
            REPOSITORY_ROOT / 'scopes/ada/web/application/ada-generic-application/pyproject.toml',
        ))
    found: list[tuple[str, str]] = []
    for name, path in constraints:
        if path.is_file():
            found.append((name, python_requirement(path)))
    exact = {requirement for _, requirement in found if requirement.startswith('==')}
    if len(exact) > 1:
        details = ', '.join(f'{name}: {requirement}' for name, requirement in found)
        return [f'Conflicting Python requirements: {details}']
    return []


# La calificación portable instala offline en un entorno temporal limpio.
def run_probe(
    *,
    python: Path,
    profile: str,
    application: Path,
    timeout: int,
    portable: bool,
) -> dict[str, object]:
    environment = {
        'PATH': os.environ.get('PATH', ''),
        'ATLANTICUS_ENVIRONMENT': 'local',
        'ADA_MANAGER_PERSISTENCE_PROVIDER': 'disabled',
    }
    for key in ('SYSTEMROOT', 'WINDIR', 'LD_LIBRARY_PATH'):
        if key in os.environ:
            environment[key] = os.environ[key]
    with tempfile.TemporaryDirectory(prefix='atlanticus-web-qualification-') as runtime_dir:
        root = Path(runtime_dir)
        environment['HOME'] = runtime_dir
        environment['APPLICATION_PUBLICATIONS_ROOT'] = str(root / 'publications')
        environment['STARTER_QUALIFICATION_LOCAL_ROOT'] = runtime_dir
        if portable:
            uv = shutil.which('uv')
            if uv is None:
                return {'status': 'BLOCKED', 'errors': ['uv executable is unavailable']}
            venv = root / 'venv'
            created = subprocess.run(
                [uv, '--no-cache', '--offline', 'venv', '--python', str(python), str(venv)],
                cwd=application,
                env=environment,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if created.returncode != 0:
                return {'status': 'FAIL', 'errors': ['Offline virtualenv creation failed'],
                        'stderr_tail': created.stderr[-1500:]}
            installed_python = (
                venv / 'Scripts/python.exe' if os.name == 'nt' else venv / 'bin/python'
            )
            installed = subprocess.run(
                [uv, '--no-cache', '--offline', 'pip', 'install', '--python',
                 str(installed_python), '--no-index', '--find-links',
                 str(application / 'wheelhouse'), '-e', str(application)],
                cwd=application,
                env=environment,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if installed.returncode != 0:
                return {'status': 'FAIL', 'errors': ['Offline wheelhouse install failed'],
                        'stderr_tail': installed.stderr[-1500:]}
            python = installed_python
        process = subprocess.run(
            [str(python), '-I', str(PROBE), '--profile', profile,
             '--application', str(application), *(['--portable'] if portable else [])],
            cwd=application,
            env=environment,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    prefix = 'STARTER_QUALIFICATION_RESULT:'
    lines = [line.removeprefix(prefix) for line in process.stdout.splitlines()
             if line.startswith(prefix)]
    if not lines:
        return {
            'status': 'FAIL',
            'errors': ['Starter runtime did not produce a qualification result'],
            'process_returncode': process.returncode,
            'stderr_tail': process.stderr[-1500:],
        }
    try:
        result = json.loads(lines[-1])
    except ValueError:
        return {'status': 'FAIL', 'errors': ['Starter runtime result is invalid JSON']}
    if process.returncode != 0:
        result['status'] = 'FAIL'
    return result


# Se diferencian explícitamente preflight, smoke de fuentes y calificación portable.
def qualify(
    *, application: Path, profile: str, python: Path, timeout: int,
    portable: bool, inspect_only: bool,
) -> dict[str, object]:
    application = application.expanduser().resolve()
    # La ruta del intérprete es lógica: resolver el symlink de un venv ejecutaría Python fuera del venv.
    python = python.expanduser().absolute()
    errors = verify_manifest(application, profile)
    if not errors:
        errors.extend(python_conflicts(application, profile))
    if portable:
        wheelhouse = application / 'wheelhouse'
        if not wheelhouse.is_dir() or not tuple(wheelhouse.glob('*.whl')):
            errors.append('Portable qualification requires a populated wheelhouse')
    if errors:
        return {'status': 'BLOCKED', 'profile': profile, 'application': str(application),
                'errors': errors}
    if inspect_only:
        return {'status': 'PRECHECK_PASS', 'profile': profile, 'application': str(application),
                'runtime': 'UNVERIFIED'}
    if not python.exists():
        return {'status': 'BLOCKED', 'profile': profile,
                'errors': ['Qualification Python interpreter does not exist']}
    try:
        result = run_probe(python=python, profile=profile, application=application,
                           timeout=timeout, portable=portable)
    except (OSError, subprocess.TimeoutExpired) as error:
        result = {'status': 'FAIL', 'errors': [type(error).__name__]}
    return {'profile': profile, 'application': str(application),
            'qualification': 'PORTABLE' if portable else 'SOURCE_SMOKE', **result}


# La salida JSON permite registrar evidencia sin introducir cambios en el repositorio.
def main() -> None:
    parser = argparse.ArgumentParser(description='Qualify a generated Atlanticus Web Starter')
    parser.add_argument('--profile', choices=('generic', 'ada'), required=True)
    parser.add_argument('--application', type=Path)
    parser.add_argument('--python', type=Path, default=Path(sys.executable))
    parser.add_argument('--timeout', type=int, default=90)
    parser.add_argument('--portable', action='store_true')
    parser.add_argument('--inspect-only', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    application = args.application or (
        REPOSITORY_ROOT / 'distribution' / f'{args.profile}-web-starter'
    )
    result = qualify(application=application, profile=args.profile, python=args.python,
                     timeout=args.timeout, portable=args.portable,
                     inspect_only=args.inspect_only)
    encoded = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + '\n'
    print(encoded, end='')
    if args.report is not None:
        report_path = args.report.expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(encoded, encoding='utf-8')
    raise SystemExit(0 if result['status'] in ('PASS', 'PRECHECK_PASS') else 2)


if __name__ == '__main__':
    main()
