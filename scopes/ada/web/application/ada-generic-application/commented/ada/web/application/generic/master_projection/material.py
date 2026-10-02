from __future__ import annotations

# Material exclusivo para Master Projection; no se comparte con Manager ni otros módulos.

import argparse
import base64
import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import struct
import sys
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

_PURPOSE = 'atlanticus.master-projection'
_MEMBER = 'master-projection.json'
_VERSION = 1
_ACTIONS = ('projection.preview', 'projection.apply', 'users.replace')
_ARCHIVE_LIMIT = 24576
_MEMBER_LIMIT = 8192
_SCRYPT_N = 32768
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_MEMORY = 67108864


# Error específico del material; nunca incluir contraseñas en sus mensajes.
class MasterMaterialError(RuntimeError):
    pass


class MasterMaterialAvailability(StrEnum):
    ABSENT = 'ABSENT'
    PRESENT = 'PRESENT'
    INVALID = 'INVALID'


@dataclass(frozen=True, slots=True)
class MasterMaterialIdentity:
    material_id: str
    service_user: str
    application_namespace: str
    environment: str
    allowed_actions: tuple[str, ...]


def _label(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise MasterMaterialError(f'{field} must be a string')
    normalized = value.strip()
    if not normalized or len(normalized) > 128 or any(ord(char) < 32 for char in normalized):
        raise MasterMaterialError(f'{field} is invalid')
    return normalized


def _password_bytes(password: str) -> bytes:
    if not isinstance(password, str):
        raise MasterMaterialError('Master Projection password is invalid')
    encoded = password.encode('utf-8')
    if len(encoded) < 16 or len(encoded) > 1024:
        raise MasterMaterialError('Master Projection password must contain 16 to 1024 bytes')
    return encoded


# El hash independiente protege el verificador incluso dentro del ZIP cifrado.
def _hash_password(password: bytes, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password, salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
        dklen=32, maxmem=_SCRYPT_MEMORY,
    )


# Se admite exactamente un miembro AES; se rechazan formatos ZIP débiles o añadidos.
def _archive_metadata(archive: zipfile.ZipFile) -> None:
    members = archive.infolist()
    if len(members) != 1 or members[0].filename != _MEMBER:
        raise MasterMaterialError('Unexpected Master Projection archive contents')
    member = members[0]
    if member.is_dir() or member.file_size > _MEMBER_LIMIT or not member.flag_bits & 1:
        raise MasterMaterialError('Master Projection archive encryption is invalid')
    strength = getattr(member, 'wz_aes_strength', None)
    if member.compress_type == 99:
        strength = None
        offset = 0
        while offset + 4 <= len(member.extra):
            field, length = struct.unpack_from('<HH', member.extra, offset)
            offset += 4
            if offset + length > len(member.extra):
                break
            if field == 0x9901 and length == 7:
                version, vendor, candidate, compression = struct.unpack_from(
                    '<H2sBH', member.extra, offset,
                )
                if version in (1, 2) and vendor == b'AE' and compression == zipfile.ZIP_STORED:
                    strength = candidate
            offset += length
    elif member.compress_type != zipfile.ZIP_STORED:
        strength = None
    if strength != 3:
        raise MasterMaterialError('Master Projection requires an AES-256 ZIP member')

def inspect_master_material(path: Path) -> MasterMaterialAvailability:
    source = Path(path)
    try:
        size = source.stat().st_size
        if size == 0 or size > _ARCHIVE_LIMIT or not source.is_file():
            return MasterMaterialAvailability.INVALID
        with zipfile.ZipFile(source) as archive:
            _archive_metadata(archive)
    except FileNotFoundError:
        return MasterMaterialAvailability.ABSENT
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, MasterMaterialError):
        return MasterMaterialAvailability.INVALID
    return MasterMaterialAvailability.PRESENT


# Se congela el propósito Master, el esquema y las operaciones permitidas.
def _validate_payload(data: object) -> dict:
    fields = {
        'schema_version', 'purpose', 'material_id', 'created_at_utc', 'service_user',
        'application_namespace', 'environment', 'allowed_actions', 'password_verifier',
    }
    if not isinstance(data, dict) or set(data) != fields:
        raise MasterMaterialError('Master Projection material schema is invalid')
    if type(data['schema_version']) is not int or data['schema_version'] != _VERSION:
        raise MasterMaterialError('Unsupported Master Projection material version')
    if data['purpose'] != _PURPOSE or data['allowed_actions'] != list(_ACTIONS):
        raise MasterMaterialError('Master Projection material purpose is invalid')
    try:
        if uuid.UUID(data['material_id']).hex != data['material_id']:
            raise ValueError
        created = datetime.fromisoformat(data['created_at_utc'])
        if created.utcoffset() is None or created.utcoffset().total_seconds() != 0:
            raise ValueError
    except (TypeError, ValueError, AttributeError) as error:
        raise MasterMaterialError('Master Projection material identity is invalid') from error
    for key in ('service_user', 'application_namespace', 'environment'):
        if _label(data[key], key) != data[key]:
            raise MasterMaterialError(f'Master Projection {key} is not normalized')
    verifier = data['password_verifier']
    if not isinstance(verifier, dict) or set(verifier) != {'algorithm', 'salt', 'digest'}:
        raise MasterMaterialError('Master Projection verifier is invalid')
    if verifier['algorithm'] != 'scrypt-n32768-r8-p1-dk32':
        raise MasterMaterialError('Master Projection verifier algorithm is unsupported')
    try:
        salt = base64.b64decode(verifier['salt'], validate=True)
        digest = base64.b64decode(verifier['digest'], validate=True)
    except (ValueError, TypeError, base64.binascii.Error) as error:
        raise MasterMaterialError('Master Projection verifier encoding is invalid') from error
    if len(salt) != 16 or len(digest) != 32:
        raise MasterMaterialError('Master Projection verifier length is invalid')
    return data


# Los datos descifrados se procesan en memoria y no se publican ni persisten.
def unlock_master_material(
    path: Path, *, service_user: str, password: str,
    application_namespace: str, environment: str,
) -> MasterMaterialIdentity:
    if inspect_master_material(path) != MasterMaterialAvailability.PRESENT:
        raise MasterMaterialError('Master Projection material is unavailable')
    user = _label(service_user, 'service_user')
    target_application = _label(application_namespace, 'application_namespace')
    target_environment = _label(environment, 'environment')
    password_bytes = _password_bytes(password)
    try:
        import pyzipper

        with pyzipper.AESZipFile(str(path)) as archive:
            _archive_metadata(archive)
            member = archive.infolist()[0]
            if member.wz_aes_strength != 3:
                raise MasterMaterialError('Master Projection requires AES-256')
            archive.setpassword(password_bytes)
            content = archive.read(_MEMBER)
        if len(content) > _MEMBER_LIMIT:
            raise MasterMaterialError('Master Projection material exceeds allowed size')
        data = _validate_payload(json.loads(content.decode('utf-8')))
    except MasterMaterialError:
        raise
    except (OSError, ValueError, RuntimeError, KeyError, EOFError, UnicodeError,
            zipfile.BadZipFile, pyzipper.BadZipFile, NotImplementedError, TypeError) as error:
        raise MasterMaterialError('Master Projection material cannot be unlocked') from error
    verifier = data['password_verifier']
    salt = base64.b64decode(verifier['salt'])
    stored = base64.b64decode(verifier['digest'])
    matched = hmac.compare_digest(_hash_password(password_bytes, salt), stored)
    matched &= hmac.compare_digest(user.encode('utf-8'), data['service_user'].encode('utf-8'))
    if not matched:
        raise MasterMaterialError('Invalid Master Projection credentials')
    if (data['application_namespace'] != target_application
            or data['environment'] != target_environment):
        raise MasterMaterialError('Master Projection material does not match this environment')
    return MasterMaterialIdentity(
        material_id=data['material_id'], service_user=data['service_user'],
        application_namespace=data['application_namespace'], environment=data['environment'],
        allowed_actions=tuple(data['allowed_actions']),
    )


# Escritura mediante temporal privado y enlace exclusivo para impedir sobrescrituras.
def generate_master_material(
    path: Path, *, service_user: str, password: str,
    application_namespace: str, environment: str,
) -> MasterMaterialIdentity:
    user = _label(service_user, 'service_user')
    application = _label(application_namespace, 'application_namespace')
    selected_environment = _label(environment, 'environment')
    password_bytes = _password_bytes(password)
    destination = Path(path).expanduser().absolute()
    if not destination.parent.is_dir() or destination.exists() or destination.is_symlink():
        raise MasterMaterialError('Master Projection output must be a new file in an existing directory')
    salt = secrets.token_bytes(16)
    material_id = uuid.uuid4().hex
    payload = {
        'schema_version': _VERSION, 'purpose': _PURPOSE, 'material_id': material_id,
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'service_user': user, 'application_namespace': application,
        'environment': selected_environment, 'allowed_actions': list(_ACTIONS),
        'password_verifier': {
            'algorithm': 'scrypt-n32768-r8-p1-dk32',
            'salt': base64.b64encode(salt).decode('ascii'),
            'digest': base64.b64encode(_hash_password(password_bytes, salt)).decode('ascii'),
        },
    }
    content = (json.dumps(payload, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')
    if len(content) > _MEMBER_LIMIT:
        raise MasterMaterialError('Master Projection material exceeds allowed size')
    descriptor, temporary = tempfile.mkstemp(
        prefix=f'.{destination.name}.', suffix='.tmp', dir=destination.parent,
    )
    os.close(descriptor)
    try:
        import pyzipper

        with pyzipper.AESZipFile(
            temporary, 'w', compression=pyzipper.ZIP_STORED,
            encryption=pyzipper.WZ_AES,
        ) as archive:
            archive.setpassword(password_bytes)
            archive.setencryption(pyzipper.WZ_AES, nbits=256)
            archive.writestr(_MEMBER, content)
        os.chmod(temporary, 0o600)
        os.link(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return MasterMaterialIdentity(
        material_id=material_id, service_user=user, application_namespace=application,
        environment=selected_environment, allowed_actions=_ACTIONS,
    )


# El operador introduce la contraseña en terminal, nunca mediante argumentos de proceso.
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Generate Master Projection access material')
    parser.add_argument('action', choices=('generate',))
    parser.add_argument('--application', required=True)
    parser.add_argument('--environment', required=True)
    parser.add_argument('--user', required=True)
    parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args(argv)
    if not sys.stdin.isatty():
        parser.error('Master Projection material generation requires an interactive terminal')
    try:
        if options.output.expanduser().resolve().is_relative_to(Path.cwd().resolve()):
            raise MasterMaterialError(
                'Master Projection material must be generated outside the distributed project'
            )
        password = getpass.getpass('Master Projection password: ')
        repeated = getpass.getpass('Repeat Master Projection password: ')
        if password != repeated:
            raise MasterMaterialError('Master Projection passwords do not match')
        result = generate_master_material(
            options.output, service_user=options.user, password=password,
            application_namespace=options.application, environment=options.environment,
        )
    except (MasterMaterialError, OSError) as error:
        print(f'BLOCKED: {error}', file=sys.stderr)
        return 2
    print(json.dumps({
        'status': 'GENERATED', 'purpose': _PURPOSE, 'material_id': result.material_id,
        'output': str(options.output),
    }, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
