from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import struct
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from io import BytesIO

_PURPOSE = 'atlanticus.manager.deployment-access'
_MEMBER = 'deployment-access.json'
_VERSION = 1
_ACCESS_LEVEL = 'manager.root'
_ARCHIVE_LIMIT = 24576
_MEMBER_LIMIT = 8192
_SCRYPT_N = 32768
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_MEMORY = 67108864


class DeploymentAccessMaterialError(RuntimeError):
    pass


# La inspección distingue presencia estructural de credenciales realmente válidas.
class MaterialAvailability(StrEnum):
    ABSENT = 'ABSENT'
    PRESENT = 'PRESENT'
    INVALID = 'INVALID'
    UNAVAILABLE = 'UNAVAILABLE'


# Identidad autenticada vinculada al material, aplicación y ambiente específicos.
@dataclass(frozen=True, slots=True)
class DeploymentAccessIdentity:
    material_id: str
    service_user: str
    application_namespace: str
    environment: str
    access_level: str = _ACCESS_LEVEL


def normalized_label(value: str, field: str) -> str:
    if not isinstance(value, str):
        raise DeploymentAccessMaterialError(f'{field} must be text')
    normalized = value.strip()
    if not normalized or len(normalized) > 128 or any(ord(char) < 32 for char in normalized):
        raise DeploymentAccessMaterialError(f'{field} is invalid')
    return normalized


def _password_bytes(password: str) -> bytes:
    if not isinstance(password, str):
        raise DeploymentAccessMaterialError('Deployment access password is invalid')
    encoded = password.encode('utf-8')
    if not 16 <= len(encoded) <= 1024:
        raise DeploymentAccessMaterialError(
            'Deployment access password must contain 16 to 1024 bytes'
        )
    return encoded


def _hash_password(password: bytes, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password,
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=32,
        maxmem=_SCRYPT_MEMORY,
    )


# Solo se admite un miembro ZIP cifrado con AES-256; rechazar formatos no esperados.
def _archive_metadata(archive: zipfile.ZipFile) -> None:
    members = archive.infolist()
    if len(members) != 1 or members[0].filename != _MEMBER:
        raise DeploymentAccessMaterialError('Unexpected deployment access archive contents')
    member = members[0]
    if member.is_dir() or member.file_size > _MEMBER_LIMIT or not member.flag_bits & 1:
        raise DeploymentAccessMaterialError('Deployment access archive encryption is invalid')
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
                    '<H2sBH', member.extra, offset
                )
                if version in (1, 2) and vendor == b'AE' and compression == zipfile.ZIP_STORED:
                    strength = candidate
            offset += length
    elif member.compress_type != zipfile.ZIP_STORED:
        strength = None
    if strength != 3:
        raise DeploymentAccessMaterialError('Deployment access requires AES-256 ZIP')


def inspect_material(content: bytes) -> MaterialAvailability:
    if not isinstance(content, bytes) or not content or len(content) > _ARCHIVE_LIMIT:
        return MaterialAvailability.INVALID
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            _archive_metadata(archive)
    except OSError, ValueError, RuntimeError, zipfile.BadZipFile, DeploymentAccessMaterialError:
        return MaterialAvailability.INVALID
    return MaterialAvailability.PRESENT


# El esquema nuevo no admite las acciones de proyección heredadas de Master Projection.
def _validate_payload(data: object) -> dict[str, object]:
    fields = {
        'schema_version',
        'purpose',
        'material_id',
        'created_at_utc',
        'service_user',
        'application_namespace',
        'environment',
        'access_level',
        'password_verifier',
    }
    if not isinstance(data, dict) or set(data) != fields:
        raise DeploymentAccessMaterialError('Deployment access schema is invalid')
    if type(data['schema_version']) is not int or data['schema_version'] != _VERSION:
        raise DeploymentAccessMaterialError('Unsupported deployment access material version')
    if data['purpose'] != _PURPOSE or data['access_level'] != _ACCESS_LEVEL:
        raise DeploymentAccessMaterialError('Deployment access purpose is invalid')
    try:
        if uuid.UUID(data['material_id']).hex != data['material_id']:
            raise ValueError
        created = datetime.fromisoformat(data['created_at_utc'])
        if created.utcoffset() is None or created.utcoffset().total_seconds() != 0:
            raise ValueError
    except (TypeError, ValueError, AttributeError) as error:
        raise DeploymentAccessMaterialError('Deployment access identity is invalid') from error
    for field in ('service_user', 'application_namespace', 'environment'):
        if normalized_label(data[field], field) != data[field]:
            raise DeploymentAccessMaterialError(f'Deployment access {field} is not normalized')
    verifier = data['password_verifier']
    if not isinstance(verifier, dict) or set(verifier) != {'algorithm', 'salt', 'digest'}:
        raise DeploymentAccessMaterialError('Deployment access verifier is invalid')
    if verifier['algorithm'] != 'scrypt-n32768-r8-p1-dk32':
        raise DeploymentAccessMaterialError('Deployment access verifier algorithm is unsupported')
    try:
        salt = base64.b64decode(verifier['salt'], validate=True)
        digest = base64.b64decode(verifier['digest'], validate=True)
    except (ValueError, TypeError, base64.binascii.Error) as error:
        raise DeploymentAccessMaterialError(
            'Deployment access verifier encoding is invalid'
        ) from error
    if len(salt) != 16 or len(digest) != 32:
        raise DeploymentAccessMaterialError('Deployment access verifier length is invalid')
    return data


# Construir el ZIP directamente en memoria para permitir Storage o filesystem sin adaptadores.
def generate_material(
    *, service_user: str, password: str, application_namespace: str, environment: str
) -> tuple[bytes, DeploymentAccessIdentity]:
    user = normalized_label(service_user, 'service_user')
    application = normalized_label(application_namespace, 'application_namespace')
    target_environment = normalized_label(environment, 'environment')
    secret = _password_bytes(password)
    material_id = uuid.uuid4().hex
    salt = secrets.token_bytes(16)
    payload = {
        'schema_version': _VERSION,
        'purpose': _PURPOSE,
        'material_id': material_id,
        'created_at_utc': datetime.now(UTC).isoformat(),
        'service_user': user,
        'application_namespace': application,
        'environment': target_environment,
        'access_level': _ACCESS_LEVEL,
        'password_verifier': {
            'algorithm': 'scrypt-n32768-r8-p1-dk32',
            'salt': base64.b64encode(salt).decode('ascii'),
            'digest': base64.b64encode(_hash_password(secret, salt)).decode('ascii'),
        },
    }
    content = (json.dumps(payload, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')
    if len(content) > _MEMBER_LIMIT:
        raise DeploymentAccessMaterialError('Deployment access material exceeds allowed size')
    import pyzipper

    output = BytesIO()
    with pyzipper.AESZipFile(
        output, 'w', compression=pyzipper.ZIP_STORED, encryption=pyzipper.WZ_AES
    ) as archive:
        archive.setpassword(secret)
        archive.setencryption(pyzipper.WZ_AES, nbits=256)
        archive.writestr(_MEMBER, content)
    material = output.getvalue()
    if inspect_material(material) is not MaterialAvailability.PRESENT:
        raise DeploymentAccessMaterialError('Generated deployment access material is invalid')
    return material, DeploymentAccessIdentity(material_id, user, application, target_environment)


# Desencriptar, validar propósito y verificar usuario y contraseña con comparaciones seguras.
def unlock_material(
    content: bytes,
    *,
    service_user: str,
    password: str,
    application_namespace: str,
    environment: str,
) -> DeploymentAccessIdentity:
    if inspect_material(content) is not MaterialAvailability.PRESENT:
        raise DeploymentAccessMaterialError('Deployment access material is unavailable')
    user = normalized_label(service_user, 'service_user')
    application = normalized_label(application_namespace, 'application_namespace')
    target_environment = normalized_label(environment, 'environment')
    secret = _password_bytes(password)
    import pyzipper

    try:
        with pyzipper.AESZipFile(BytesIO(content)) as archive:
            _archive_metadata(archive)
            if archive.infolist()[0].wz_aes_strength != 3:
                raise DeploymentAccessMaterialError('Deployment access requires AES-256 ZIP')
            archive.setpassword(secret)
            raw = archive.read(_MEMBER)
        if len(raw) > _MEMBER_LIMIT:
            raise DeploymentAccessMaterialError('Deployment access material exceeds allowed size')
        data = _validate_payload(json.loads(raw.decode('utf-8')))
    except DeploymentAccessMaterialError:
        raise
    except (
        OSError,
        ValueError,
        RuntimeError,
        KeyError,
        EOFError,
        UnicodeError,
        zipfile.BadZipFile,
        pyzipper.BadZipFile,
        NotImplementedError,
        TypeError,
    ) as error:
        raise DeploymentAccessMaterialError(
            'Deployment access material cannot be unlocked'
        ) from error
    verifier = data['password_verifier']
    salt = base64.b64decode(verifier['salt'])
    digest = base64.b64decode(verifier['digest'])
    credentials_match = hmac.compare_digest(_hash_password(secret, salt), digest)
    credentials_match &= hmac.compare_digest(
        user.encode('utf-8'), data['service_user'].encode('utf-8')
    )
    if not credentials_match:
        raise DeploymentAccessMaterialError('Invalid deployment access credentials')
    if data['application_namespace'] != application or data['environment'] != target_environment:
        raise DeploymentAccessMaterialError(
            'Deployment access material does not match this environment'
        )
    return DeploymentAccessIdentity(
        material_id=data['material_id'],
        service_user=data['service_user'],
        application_namespace=data['application_namespace'],
        environment=data['environment'],
    )
