from __future__ import annotations

# Genera los perfiles Web sin solicitar archivos de configuración externos.
# El .env.detail canónico contiene el inventario y las anotaciones de distribución.

import argparse
import csv
import hashlib
import io
import json
import re
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = WEB_ROOT.parents[2]
STARTER_ROOT = WEB_ROOT / 'starter'
_PROFILES = ('generic', 'ada')
_ENV_ASSIGNMENT = re.compile(r'^([A-Z][A-Z0-9_]*)=(.*)$')
_DISTRIBUTION = re.compile(
    r'^# @distribution (manual|manual-default|manual-local|key-vault)(?: (\S+))?$'
)
_CONFIGURATION_TEMPLATES = (
    'configuration/templates/dev.mapping-env.csv',
    'configuration/templates/uat.mapping-env.csv',
    'configuration/templates/prd.mapping-env.csv',
    'configuration/templates/secrets.json',
)


# Los registros mantienen un único origen de las variables para ambos formatos.
@dataclass(frozen=True)
class EnvironmentEntry:
    name: str
    mode: str
    value: str
    secret_reference: str | None


# Sólo se distribuyen archivos productivos; se excluyen espejos pedagógicos y pruebas.
def _copy_product_files(source: Path, destination: Path) -> None:
    for path in sorted(source.rglob('*')):
        if (
            not path.is_file()
            or {'commented', 'tests', '__pycache__', '.pytest_cache'}
            & set(path.relative_to(source).parts)
            or path.suffix == '.pyc'
        ):
            continue
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        if path.suffix == '.sh':
            target.chmod(target.stat().st_mode | stat.S_IXUSR)


# Un dato activo sin clasificación o con duplicados bloquea el artifact antes de crearlo.
# Las alternativas comentadas se conservan en .env.detail, pero no se activan solas.
def _environment_entries(contract: Path) -> tuple[EnvironmentEntry, ...]:
    entries: list[EnvironmentEntry] = []
    names: set[str] = set()
    pending: tuple[str, str | None] | None = None
    for line in contract.read_text(encoding='utf-8').splitlines():
        declaration = _DISTRIBUTION.fullmatch(line)
        if declaration is not None:
            if pending is not None:
                raise ValueError('ADA environment distribution declaration has no variable')
            pending = declaration.group(1), declaration.group(2)
            continue
        assignment = _ENV_ASSIGNMENT.fullmatch(line)
        if assignment is None:
            if pending is not None:
                raise ValueError('ADA environment distribution declaration must precede its variable')
            continue
        if pending is None:
            raise ValueError(f'ADA environment variable has no distribution declaration: {assignment[1]}')
        name, value = assignment.groups()
        mode, secret_reference = pending
        pending = None
        if name in names:
            raise ValueError(f'ADA environment variable is duplicated: {name}')
        if re.search(r'(KEY|SECRET|TOKEN|PASSWORD|SAS|CONNECTION_STRING)', name) and (
            value and not (value.startswith('<') and value.endswith('>'))
        ):
            raise ValueError(f'ADA environment contract exposes a credential: {name}')
        if mode == 'key-vault':
            if secret_reference is None:
                raise ValueError(f'Key Vault reference is missing for {name}')
            if value and not (value.startswith('<') and value.endswith('>')):
                raise ValueError(f'Key Vault variable contains a non-placeholder value: {name}')
        elif secret_reference is not None:
            raise ValueError(f'Manual variable cannot declare a Key Vault reference: {name}')
        if mode in ('manual-default', 'manual-local') and (
            not value or '<' in value or re.search(r'(KEY|SECRET|TOKEN|PASSWORD|SAS)', name)
        ):
            raise ValueError(f'Unsafe environment default for {name}')
        names.add(name)
        entries.append(EnvironmentEntry(name, mode, value, secret_reference))
    if pending is not None or not entries:
        raise ValueError('ADA environment contract has incomplete or missing distribution entries')
    return tuple(entries)


# Sólo los defaults marcados expresamente se trasladan a los archivos generados.
def _manual_value(entry: EnvironmentEntry, environment: str | None) -> str:
    if entry.mode == 'manual-default':
        return entry.value
    if entry.mode == 'manual-local' and environment == 'dev':
        return entry.value
    return ''


# Los CSV respetan exactamente las tres columnas del ejemplo del consumidor.
def _mapping(entries: tuple[EnvironmentEntry, ...], environment: str) -> str:
    output = io.StringIO(newline='')
    writer = csv.writer(output, lineterminator='\n')
    output.write('envName, secretReference, explicitValue\n')
    for entry in entries:
        writer.writerow((
            entry.name,
            entry.secret_reference or '',
            _manual_value(entry, environment),
        ))
    # Marcador terminal exigido por el pipeline; no corresponde a una variable.
    output.write('END_NO_READ,,')
    return output.getvalue()


# El JSON conserva las cuatro propiedades del ejemplo, sin cargar secretos inline.
# exists_in_key_vault señala el modo de resolución esperado, no verifica el vault.
def _secrets(entries: tuple[EnvironmentEntry, ...]) -> str:
    return json.dumps(
        [
            {
                'var_name': entry.name,
                'secret_name': entry.secret_reference,
                'value': _manual_value(entry, None) or None,
                'exists_in_key_vault': entry.mode == 'key-vault',
            }
            for entry in entries
        ],
        indent=2,
        ensure_ascii=False,
    ) + '\n'


# El destino generado sigue siendo editable y se niega a sobrescribir otro existente.
def generate_starter(*, profile: str, destination: Path) -> Path:
    if profile not in _PROFILES:
        raise ValueError('Unknown Web Starter profile')
    destination = destination.expanduser().resolve()
    if destination.exists():
        raise FileExistsError('Web Starter destination already exists')
    canonical_env_detail = (
        REPOSITORY_ROOT / 'scopes/ada/web/application/ada-generic-application/.env.detail'
    )
    entries = ()
    if profile == 'ada':
        if not canonical_env_detail.is_file():
            raise FileNotFoundError('ADA Generic environment contract is missing')
        entries = _environment_entries(canonical_env_detail)
    destination.mkdir(parents=True)
    _copy_product_files(STARTER_ROOT / 'base', destination)
    if profile == 'ada':
        _copy_product_files(STARTER_ROOT / 'ada', destination)
        shutil.copyfile(canonical_env_detail, destination / '.env.detail')
        for environment in ('dev', 'uat', 'prd'):
            target = destination / f'configuration/templates/{environment}.mapping-env.csv'
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(_mapping(entries, environment), encoding='utf-8')
        target = destination / 'configuration/templates/secrets.json'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_secrets(entries), encoding='utf-8')
    hashes = {
        path.relative_to(destination).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(destination.rglob('*'))
        if path.is_file()
    }
    (destination / 'manifest.json').write_text(
        json.dumps(
            {
                'artifact_kind': 'web-application-starter',
                'profile': profile,
                'qualification': 'UNVERIFIED',
                'wheelhouse_included': False,
                'configuration_templates': list(_CONFIGURATION_TEMPLATES) if profile == 'ada' else [],
                'files': hashes,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + '\n',
        encoding='utf-8',
    )
    return destination


# La CLI requiere únicamente el perfil y, opcionalmente, el destino.
def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', choices=_PROFILES, required=True)
    parser.add_argument('--destination', type=Path)
    args = parser.parse_args()
    destination = args.destination or (
        REPOSITORY_ROOT / 'distribution' / f'{args.profile}-web-starter'
    )
    print(generate_starter(profile=args.profile, destination=destination))


if __name__ == '__main__':
    main()
