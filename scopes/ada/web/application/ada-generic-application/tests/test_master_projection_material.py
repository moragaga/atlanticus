from __future__ import annotations

import json
import struct
import zipfile

import pytest

from ada.web.application.generic.master_projection.material import (
    MasterMaterialAvailability,
    MasterMaterialError,
    _hash_password,
    _password_bytes,
    generate_master_material,
    inspect_master_material,
    unlock_master_material,
)

_PASSWORD = 'Long-master-password-2026!'


def _generate(tmp_path):
    target = tmp_path / 'master-projection.zip'
    identity = generate_master_material(
        target,
        service_user='master-service',
        password=_PASSWORD,
        application_namespace='example',
        environment='production',
    )
    return target, identity


def _unlock(
    target,
    *,
    password=_PASSWORD,
    user='master-service',
    application='example',
    environment='production',
):
    return unlock_master_material(
        target,
        password=password,
        service_user=user,
        application_namespace=application,
        environment=environment,
    )


def test_password_length_is_checked_before_archive_generation():
    with pytest.raises(MasterMaterialError, match='16 to 1024'):
        _password_bytes('short')
    assert len(_hash_password(b'Long-master-password-2026!', b'0123456789ABCDEF')) == 32


def test_absent_material_is_not_an_authentication_bypass(tmp_path):
    target = tmp_path / 'missing.zip'
    assert inspect_master_material(target) is MasterMaterialAvailability.ABSENT
    with pytest.raises(MasterMaterialError, match='unavailable'):
        _unlock(target)


def test_unencrypted_archive_is_rejected(tmp_path):
    target = tmp_path / 'plain.zip'
    with zipfile.ZipFile(target, 'w') as archive:
        archive.writestr('master-projection.json', '{}')
    assert inspect_master_material(target) is MasterMaterialAvailability.INVALID
    with pytest.raises(MasterMaterialError, match='unavailable'):
        _unlock(target)


def test_round_trip_is_exclusively_for_master_projection(tmp_path):
    import pyzipper

    target, generated = _generate(tmp_path)
    assert inspect_master_material(target) is MasterMaterialAvailability.PRESENT
    assert generated.material_id == _unlock(target).material_id
    assert _unlock(target) == _unlock(target)
    assert _unlock(target).allowed_actions == (
        'projection.preview',
        'projection.apply',
        'users.replace',
    )
    with pyzipper.AESZipFile(str(target)) as archive:
        assert archive.namelist() == ['master-projection.json']
        assert archive.getinfo('master-projection.json').wz_aes_strength == 3
        archive.setpassword(_PASSWORD.encode())
        manifest = json.loads(archive.read('master-projection.json'))
    assert manifest['purpose'] == 'atlanticus.master-projection'
    assert 'password' not in manifest
    assert manifest['password_verifier']['algorithm'] == 'scrypt-n32768-r8-p1-dk32'
    assert manifest['password_verifier']['digest'] != _PASSWORD
    raw = target.read_bytes()
    assert _PASSWORD.encode() not in raw
    assert b'master-service' not in raw


def test_wrong_credentials_and_cross_environment_are_rejected(tmp_path):
    target, _ = _generate(tmp_path)
    with pytest.raises(MasterMaterialError):
        _unlock(target, password='An-entirely-different-password')
    with pytest.raises(MasterMaterialError, match='credentials'):
        _unlock(target, user='another-service')
    with pytest.raises(MasterMaterialError, match='does not match'):
        _unlock(target, environment='local')
    with pytest.raises(MasterMaterialError, match='does not match'):
        _unlock(target, application='different-app')


def test_generation_never_overwrites_existing_material(tmp_path):
    target, _ = _generate(tmp_path)
    previous = target.read_bytes()
    with pytest.raises(MasterMaterialError, match='new file'):
        generate_master_material(
            target,
            service_user='master-service',
            password=_PASSWORD,
            application_namespace='example',
            environment='production',
        )
    assert target.read_bytes() == previous


def test_ciphertext_tampering_is_detected_only_after_unlock(tmp_path):
    target, _ = _generate(tmp_path)
    altered = bytearray(target.read_bytes())
    assert altered[:4] == b'PK\x03\x04'
    _, _, _, _, _, _, _, _, _, name_length, extra_length = struct.unpack_from(
        '<IHHHHHIIIHH',
        altered,
    )
    ciphertext_start = 30 + name_length + extra_length + 18
    altered[ciphertext_start + 2] ^= 1
    target.write_bytes(altered)
    assert inspect_master_material(target) is MasterMaterialAvailability.PRESENT
    with pytest.raises(MasterMaterialError):
        _unlock(target)


def test_valid_password_does_not_authorize_other_zip_formats(tmp_path):
    import pyzipper

    target, _ = _generate(tmp_path)
    with pyzipper.AESZipFile(str(target)) as archive:
        archive.setpassword(_PASSWORD.encode())
        manifest = json.loads(archive.read('master-projection.json'))
    manifest['purpose'] = 'atlanticus.other-service'
    target.unlink()
    with pyzipper.AESZipFile(
        str(target),
        'w',
        compression=pyzipper.ZIP_STORED,
        encryption=pyzipper.WZ_AES,
    ) as archive:
        archive.setpassword(_PASSWORD.encode())
        archive.setencryption(pyzipper.WZ_AES, nbits=256)
        archive.writestr('master-projection.json', json.dumps(manifest))
    with pytest.raises(MasterMaterialError, match='purpose'):
        _unlock(target)
