from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

# Ubicacion del tooling compartido y la aplicacion original; el origen no se modifica.
TOOLING_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = TOOLING_ROOT.parents[4]
PROJECT_ROOT = REPOSITORY_ROOT / 'scopes/ada/web/application/ada-integrated-operations-application'
GENERIC_ROOT = REPOSITORY_ROOT / 'scopes/ada/web/application/ada-generic-application'
BASE_STARTER = REPOSITORY_ROOT / 'tooling/distribution/web/starter/base'
ADA_STARTER = TOOLING_ROOT / 'starter'
sys.path.insert(0, str(TOOLING_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / 'tooling/distribution/web'))

from native_uv_sources import prepare_native_uv_sources
from generate_starter import _copy_product_files, _environment_entries, _mapping, _secrets
from build_distribution import (
    AdaDistributionError,
    _build_internal,
    _build_project_tooling,
    _sha256,
    _write_external_requirements,
    _write_host_requirements,
    _write_starter_build_requirements,
    wheels,
)
from qualify_distribution import qualify_ada_distribution

# Inventario de claves activas y opcionales documentadas por ADA y Operaciones Integradas.
PRODUCT = 'ada-integrated-operations-application'
MODES = {
    'ATLANTICUS_ENVIRONMENT': 'environment',
    'ATLANTICUS_WEB_PORT': 'manual',
    'ATLANTICUS_WEB_ASSETS_OPTIMIZED': 'manual',
    'ATLANTICUS_WEB_SLOW_REQUEST_THRESHOLD_MS': 'manual-default',
    'ATLANTICUS_OBSERVABILITY_FILE_LOGS_ENABLED': 'manual-default',
    'ATLANTICUS_AZURE_OBSERVABILITY_MODE': 'manual',
    'ATLANTICUS_AZURE_OBSERVABILITY_PROFILE': 'manual',
    'APPLICATION_INSIGHTS_CONNECTION_STRING': 'manual',
    'ADA_CONTENT_STATE_PRESENTATION_MODE': 'manual-default',
    'ADA_PERSISTENCE_MODE': 'manual-default',
    'ADA_APPLICATION_NAMESPACE': 'manual-default',
    'ADA_TOOL_NAMESPACE': 'manual-default',
    'ADA_TOOL_ADOPTION_MODE': 'manual-default',
    'ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID': 'manual',
    'ADA_TOOL_LOCAL_BASE_ROOT': 'manual',
    'ADA_STORAGE_CONTAINER_NAME': 'manual-default',
    'ADA_STORAGE_CONNECTION_STRING': 'key-vault secret-ada-storage-connection-string',
    'ADA_STORAGE_ACCOUNT_URL': 'manual',
    'ADA_STORAGE_SAS_TOKEN': 'manual',
    'ADA_COSMOS_ENDPOINT': 'key-vault secret-cosmos-endpoint',
    'ADA_COSMOS_KEY': 'key-vault secret-cosmos-primary-key',
    'ADA_COSMOS_DATABASE_NAME': 'key-vault secret-cosmos-sql-database-name',
    'COSMOS_CONSUMPTION_ENDPOINT': 'manual',
    'COSMOS_CONSUMPTION_KEY': 'manual',
    'COSMOS_CONSUMPTION_DATABASE_NAME': 'manual',
}
_ASSIGNMENT = re.compile(r'^\s*(#\s*)?([A-Z][A-Z0-9_]*)=(.*)$')

# La composicion del worker WSGI usa el mismo descriptor que la CLI local.
RUNTIME = '''from ada.web.application.generic.host import create_worker_runtime as create_ada_worker_runtime
from ada.web.application.generic.host import run_operational_application
from ada.web.application.integrated_operations.composition import create_integrated_operations_extension
from ada.web.application.integrated_operations.descriptor import INTEGRATED_OPERATIONS_APPLICATION_DESCRIPTOR

from application.production import create_identity_provider


def create_worker_runtime():
    return create_ada_worker_runtime(
        application_descriptor=INTEGRATED_OPERATIONS_APPLICATION_DESCRIPTOR,
        extension_factory=create_integrated_operations_extension,
        production_identity_provider_factory=create_identity_provider,
    )


def run_application() -> None:
    run_operational_application(
        application_descriptor=INTEGRATED_OPERATIONS_APPLICATION_DESCRIPTOR,
        extension_factory=create_integrated_operations_extension,
        production_identity_provider_factory=create_identity_provider,
    )
'''


# Conserva los comentarios de opciones deshabilitadas y genera el inventario de templates.
def _environment_contract(specialized: str, generic: str) -> tuple[str, str]:
    known: dict[str, tuple[str, str, bool]] = {}
    readable = list(specialized.splitlines())
    for line in readable:
        match = _ASSIGNMENT.fullmatch(line)
        if match is not None:
            name = match.group(2)
            if name in known:
                raise ValueError(f'Duplicate environment variable: {name}')
            known[name] = (line, match.group(3), match.group(1) is None)
    unknown = set(known) - set(MODES)
    if unknown:
        raise ValueError(f'Undeclared environment variables: {", ".join(sorted(unknown))}')
    inherited = []
    generic_lines = generic.splitlines()
    for index, line in enumerate(generic_lines):
        match = _ASSIGNMENT.fullmatch(line)
        if match is None:
            continue
        name = match.group(2)
        if name in MODES and name not in known:
            known[name] = (line, match.group(3), match.group(1) is None)
            context = []
            for previous in reversed(generic_lines[:index]):
                if not previous.startswith('# ') or _ASSIGNMENT.fullmatch(previous):
                    break
                context.append(previous)
            inherited.extend((*reversed(context), line))
    missing = set(MODES) - set(known)
    if missing:
        raise ValueError(f'Missing documented environment variables: {", ".join(sorted(missing))}')
    if inherited:
        readable.extend(('', '# Opciones adicionales documentadas en ADA Generic.', *inherited))
    normalized = []
    for name, mode in MODES.items():
        _, value, active = known[name]
        if mode == 'environment' and value != 'local':
            raise ValueError('ATLANTICUS_ENVIRONMENT must default to local')
        if mode == 'manual-default' and not active:
            raise ValueError(f'Environment default must be enabled: {name}')
        if mode == 'manual-default' and not value:
            raise ValueError(f'Environment default is missing: {name}')
        if name == 'ADA_TOOL_ADOPTION_MODE' and value not in {'startup', 'on_page_load'}:
            raise ValueError('ADA_TOOL_ADOPTION_MODE must be startup or on_page_load')
        if mode.startswith('key-vault') and active:
            raise ValueError(f'Environment secret must remain disabled in the example: {name}')
        if not active and not mode.startswith('key-vault'):
            value = ''
        normalized.extend((f'# @distribution {mode}', f'{name}={value}'))
    return '\n'.join(readable).rstrip() + '\n', '\n'.join(normalized) + '\n'


# Copia el proyecto como paquete raiz editable e integra el host sin duplicar el codigo.
def _portable_pyproject(source: str) -> str:
    result = re.sub(r'(?ms)^\[tool\.uv\.sources\]\n.*?(?=^\[|\Z)', '', source)
    if '[tool.uv.sources]' in result:
        raise ValueError('Editable source declarations remain in portable project')
    old = 'include = ["ada.web.application.integrated_operations*"]'
    if result.count(old) != 1:
        raise ValueError('Integrated Operations setuptools package declaration has changed')
    result = result.replace(old, 'include = ["ada.web.application.integrated_operations*", "application*"]')
    return result


# Los fuentes productivos viven directamente en src; se excluyen tests y commented.
def _copy_application_source(destination: Path) -> None:
    source = PROJECT_ROOT / 'src'
    if not source.is_dir():
        raise FileNotFoundError('Integrated Operations source directory is missing')
    shutil.copytree(
        source,
        destination / 'src',
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'),
    )
    project = destination / 'pyproject.toml'
    project.write_text(
        _portable_pyproject((PROJECT_ROOT / 'pyproject.toml').read_text(encoding='utf-8')),
        encoding='utf-8',
    )


# Se calcula la lista de archivos antes de construir las ruedas de distribucion.
def _write_source_manifest(destination: Path) -> None:
    manifest = {
        'artifact_kind': 'web-application-starter',
        'profile': 'ada',
        'application': PRODUCT,
        'editable_source': 'src',
        'qualification': 'UNVERIFIED',
        'wheelhouse_included': False,
        'configuration_templates': [
            'configuration/templates/dev.mapping-env.csv',
            'configuration/templates/uat.mapping-env.csv',
            'configuration/templates/prd.mapping-env.csv',
            'configuration/templates/secrets.json',
        ],
        'files': {
            path.relative_to(destination).as_posix(): _sha256(path)
            for path in sorted(destination.rglob('*'))
            if path.is_file() and path.name != 'manifest.json'
        },
    }
    (destination / 'manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
        encoding='utf-8',
    )


# Se reutilizan los archivos base de Docker de ADA y se agrega la aplicacion real.
def _starter(destination: Path) -> None:
    if destination.exists():
        raise FileExistsError('Export destination already exists')
    destination.mkdir(parents=True)
    _copy_product_files(
        BASE_STARTER,
        destination,
        excluded_roots=(Path('docker'), Path('src/application/modules'), Path('src/application/pages')),
    )
    _copy_product_files(ADA_STARTER, destination)
    root = destination / 'src/application'
    root.mkdir(parents=True, exist_ok=True)
    (root / 'runtime.py').write_text(RUNTIME, encoding='utf-8')
    for relative in ('composition.py', 'pages', 'modules'):
        unused = root / relative
        if unused.is_dir():
            shutil.rmtree(unused)
        elif unused.is_file():
            unused.unlink()
    _copy_application_source(destination)
    # No se conserva el .env local ni se debe registrar la configuracion real en Git.
    (destination / '.gitignore').write_text(
        '.env\n.venv/\n__pycache__/\n.pytest_cache/\n.ruff_cache/\n'
        '.runtime/\ndist/\nbuild/\n*.pyc\n', encoding='utf-8'
    )
    specialized = (PROJECT_ROOT / '.env.detail').read_text(encoding='utf-8')
    generic = (GENERIC_ROOT / '.env.detail').read_text(encoding='utf-8')
    readable, normalized = _environment_contract(specialized, generic)
    (destination / '.env.detail').write_text(readable, encoding='utf-8')
    with tempfile.TemporaryDirectory() as temporary:
        temporary_path = Path(temporary) / 'env.contract'
        temporary_path.write_text(normalized, encoding='utf-8')
        entries = _environment_entries(temporary_path)
    templates = destination / 'configuration/templates'
    templates.mkdir(parents=True, exist_ok=True)
    for stage in ('dev', 'uat', 'prd'):
        (templates / f'{stage}.mapping-env.csv').write_text(
            _mapping(entries, stage), encoding='utf-8'
        )
    (templates / 'secrets.json').write_text(_secrets(entries), encoding='utf-8')
    tooling = destination / 'tooling'
    tooling.mkdir(exist_ok=True)
    template_root = TOOLING_ROOT / 'templates/integrated_operations'
    for name in ('install_local.sh', 'run_local.sh'):
        shutil.copy2(template_root / name, tooling / name)
    _write_source_manifest(destination)



# Garantiza que el wheel de la raiz contiene los recursos CSS y JS actualmente presentes.
# Verifica contratos de recursos dentro de cada wheel antes de entregar el wheelhouse.
def _validate_packaged_asset_lists(wheelhouse: Path) -> None:
    for wheel in sorted(wheelhouse.glob('*.whl')):
        with zipfile.ZipFile(wheel) as archive:
            names = {name for name in archive.namelist() if not name.endswith('/')}
            manifests = sorted(
                name for name in names
                if name.endswith(('/resources/css/css.list', '/resources/js/js.list'))
            )
            for manifest in manifests:
                kind = manifest.rsplit('/', 1)[-1].removesuffix('.list')
                prefix = manifest.rsplit('/', 1)[0] + '/'
                actual = {
                    name.removeprefix(prefix)
                    for name in names
                    if name.startswith(prefix) and name != manifest
                }
                listed = [
                    line.strip()
                    for line in archive.read(manifest).decode('utf-8').splitlines()
                    if line.strip() and not line.strip().startswith('#')
                ]
                declared = set(listed)
                if actual == declared and len(listed) == len(declared):
                    continue
                unlisted = sorted(actual - declared)
                missing = sorted(declared - actual)
                repeated = len(listed) - len(declared)
                raise AdaDistributionError(
                    f'Packaged {kind.upper()} asset inventory mismatch: {wheel.name}: '
                    f'{manifest}; unlisted={unlisted}; missing={missing}; duplicates={repeated}'
                )


def _verify_source_wheel(uv: str, destination: Path) -> None:
    with tempfile.TemporaryDirectory(prefix='.ada-integrated-wheel-', dir=destination) as temporary:
        output = Path(temporary)
        result = subprocess.run(
            [uv, 'build', '--wheel', '--no-sources', '--python', sys.executable,
             '--out-dir', str(output), str(destination)],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        wheels_built = list(output.glob('*.whl'))
        if result.returncode != 0 or len(wheels_built) != 1:
            raise AdaDistributionError('Editable Integrated Operations wheel build failed')
        required = {
            'application/wsgi.py',
            'application/runtime.py',
            'ada/web/application/integrated_operations/__main__.py',
        }
        source = destination / 'src/ada/web/application/integrated_operations'
        for path in source.rglob('*'):
            if path.is_file() and 'resources' in path.parts:
                required.add(path.relative_to(destination / 'src').as_posix())
        with zipfile.ZipFile(wheels_built[0]) as archive:
            missing = required - set(archive.namelist())
            if missing:
                raise AdaDistributionError(
                    f'Integrated Operations wheel is missing resources: {", ".join(sorted(missing)[:4])}'
                )


# Se instala el paquete especializado desde src en la imagen, no desde un wheel duplicado.
def _build(destination: Path, uv: str) -> int:
    wheels._require_python()
    manifest = wheels._validate_starter(destination, 'ada')
    _verify_source_wheel(uv, destination)
    if (destination / 'wheelhouse').exists() or (destination / 'requirements').exists():
        raise ValueError('Export destination already contains a distribution')
    with tempfile.TemporaryDirectory(prefix='.ada-integrated-', dir=destination) as temporary:
        staging = Path(temporary)
        wheelhouse = staging / 'wheelhouse'
        wheelhouse.mkdir()
        external, constraints = _write_external_requirements(
            uv=uv, project=PROJECT_ROOT, staging=staging
        )
        host = _write_host_requirements(uv=uv, staging=staging, constraints=constraints)
        starter_build = _write_starter_build_requirements(
            uv=uv, staging=staging, build_requirements=wheels._build_requirements([destination])
        )
        records = _build_internal(uv=uv, project=PROJECT_ROOT, target=wheelhouse, staging=staging)
        _validate_packaged_asset_lists(wheelhouse)
        application_records = [record for record in records if record['name'] == PRODUCT]
        if len(application_records) != 1:
            raise AdaDistributionError('Integrated Operations dependency closure is incomplete')
        for record in application_records:
            (wheelhouse / record['filename']).unlink()
        records = [record for record in records if record['name'] != PRODUCT]
        tooling = _build_project_tooling(uv=uv, target=wheelhouse)
        if any(record['name'] == tooling['name'] for record in records):
            raise AdaDistributionError('Duplicate ADA project tooling package')
        records = sorted((*records, tooling), key=lambda row: row['name'])
        # Se declara la fuente de los wheels privados sin bloquear la exportación por la plataforma local.
        prepare_native_uv_sources(destination / 'pyproject.toml', wheelhouse, records)
        manifest['files']['pyproject.toml'] = _sha256(destination / 'pyproject.toml')
        requirements = staging / 'requirements'
        requirements.mkdir()
        for path in (external, host, starter_build):
            shutil.copy2(path, requirements / path.name)
        shutil.copy2(external, requirements / 'project-runtime.txt')
        revision = subprocess.run(
            ['git', 'rev-parse', 'HEAD'], cwd=REPOSITORY_ROOT,
            text=True, capture_output=True, check=True,
        ).stdout.strip()
        wheel_manifest = {
            'schema_version': 2,
            'strategy': 'internal-wheels-external-image-build',
            'python': wheels.PYTHON_VERSION,
            'profile': 'ada',
            'application': PRODUCT,
            'source_git_head': revision,
            'qualification': 'UNVERIFIED',
            'runtime_lock_sha256': _sha256(PROJECT_ROOT / 'uv.lock'),
            'requirements': {
                item.name: _sha256(item) for item in (external, host, starter_build)
            },
            'packages': records,
        }
        (wheelhouse / 'manifest.json').write_text(
            json.dumps(wheel_manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
            encoding='utf-8',
        )
        manifest['wheelhouse_included'] = True
        manifest['delivery_strategy'] = wheel_manifest['strategy']
        manifest_text = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + '\n'
        project_lock = {
            'schema_version': 1,
            'distribution_manifest_sha256': hashlib.sha256(manifest_text.encode()).hexdigest(),
            'wheelhouse_manifest_sha256': _sha256(wheelhouse / 'manifest.json'),
            'external_runtime_sha256': _sha256(external),
            'project_sha256': _sha256(destination / 'pyproject.toml'),
            'project_runtime_sha256': _sha256(requirements / 'project-runtime.txt'),
        }
        (requirements / 'project.lock.json').write_text(
            json.dumps(project_lock, ensure_ascii=False, sort_keys=True, indent=2) + '\n',
            encoding='utf-8',
        )
        wheelhouse.rename(destination / 'wheelhouse')
        requirements.rename(destination / 'requirements')
        (destination / 'manifest.json').write_text(manifest_text, encoding='utf-8')
    return len(records)


# La verificacion estatica es un precheck, no una prueba de despliegue productivo.
def export_integrated_operations(destination: Path, uv: str) -> dict:
    destination = destination.expanduser().resolve()
    _starter(destination)
    count = _build(destination, uv)
    qualification = qualify_ada_distribution(destination)
    if qualification['status'] != 'PRECHECK_PASS':
        raise AdaDistributionError(
            f'Distribution precheck failed: {qualification.get("error", "unknown")}'
        )
    return {
        'status': 'PRECHECK_PASS',
        'application': PRODUCT,
        'path': str(destination),
        'internal_wheels': count,
        'docker_image': 'UNVERIFIED',
        'production_runtime': 'UNVERIFIED',
    }


# Punto de entrada local; los repositorios remotos permanecen de solo lectura.
def main() -> None:
    parser = argparse.ArgumentParser(description='Export the ADA Integrated Operations Web application')
    parser.add_argument(
        '--destination', type=Path,
        default=REPOSITORY_ROOT / 'distribution/ada-integrated-operations',
    )
    args = parser.parse_args()
    uv = shutil.which('uv')
    if uv is None:
        raise SystemExit('uv executable is required')
    try:
        result = export_integrated_operations(args.destination, uv)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(json.dumps({'status': 'BLOCKED', 'error': str(error)}, ensure_ascii=False))
        raise SystemExit(2) from error
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
