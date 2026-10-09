from __future__ import annotations

import json
import zipfile
from io import BytesIO

import pytest

from atlanticus.web.deployment_access.material import (
    DeploymentAccessMaterialError,
    MaterialAvailability,
    generate_material,
    inspect_material,
    unlock_material,
)

_PASSWORD = 'Extra-Long-Deployment-Secret-2026!'


def test_invalid_and_oversized_archives_are_not_accepted() -> None:
    assert inspect_material(b'') is MaterialAvailability.INVALID
    assert inspect_material(b'0' * 24577) is MaterialAvailability.INVALID
    output = BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('deployment-access.json', '{}')
    assert inspect_material(output.getvalue()) is MaterialAvailability.INVALID


def test_short_password_is_not_accepted() -> None:
    with pytest.raises(DeploymentAccessMaterialError, match='16 to 1024'):
        generate_material(
            service_user='operator',
            password='short',
            application_namespace='example',
            environment='production',
        )


def test_roundtrip_and_cross_environment_rejection() -> None:
    pyzipper = pytest.importorskip('pyzipper')
    content, created = generate_material(
        service_user='operator',
        password=_PASSWORD,
        application_namespace='example',
        environment='production',
    )
    assert created.access_level == 'manager.root'
    assert inspect_material(content) is MaterialAvailability.PRESENT
    unlocked = unlock_material(
        content,
        service_user='operator',
        password=_PASSWORD,
        application_namespace='example',
        environment='production',
    )
    assert unlocked == created
    with pyzipper.AESZipFile(BytesIO(content)) as archive:
        assert archive.namelist() == ['deployment-access.json']
        assert archive.infolist()[0].wz_aes_strength == 3
        archive.setpassword(_PASSWORD.encode())
        manifest = json.loads(archive.read('deployment-access.json'))
    assert manifest['purpose'] == 'atlanticus.manager.deployment-access'
    assert manifest['access_level'] == 'manager.root'
    assert 'allowed_actions' not in manifest
    assert 'password' not in manifest
    assert _PASSWORD.encode() not in content
    with pytest.raises(DeploymentAccessMaterialError, match='credentials'):
        unlock_material(
            content,
            service_user='another',
            password=_PASSWORD,
            application_namespace='example',
            environment='production',
        )
    with pytest.raises(DeploymentAccessMaterialError):
        unlock_material(
            content,
            service_user='operator',
            password='A-Different-Long-Password',
            application_namespace='example',
            environment='production',
        )
    with pytest.raises(DeploymentAccessMaterialError, match='environment'):
        unlock_material(
            content,
            service_user='operator',
            password=_PASSWORD,
            application_namespace='example',
            environment='qa',
        )
    with pytest.raises(DeploymentAccessMaterialError, match='environment'):
        unlock_material(
            content,
            service_user='operator',
            password=_PASSWORD,
            application_namespace='another',
            environment='production',
        )


def test_master_projection_material_is_not_accepted() -> None:
    pytest.importorskip('pyzipper')
    from pyzipper import WZ_AES, ZIP_STORED, AESZipFile

    output = BytesIO()
    with AESZipFile(output, 'w', compression=ZIP_STORED, encryption=WZ_AES) as archive:
        archive.setpassword(_PASSWORD.encode())
        archive.setencryption(WZ_AES, nbits=256)
        archive.writestr('master-projection.json', '{}')
    assert inspect_material(output.getvalue()) is MaterialAvailability.INVALID
    with pytest.raises(DeploymentAccessMaterialError):
        unlock_material(
            output.getvalue(),
            service_user='operator',
            password=_PASSWORD,
            application_namespace='example',
            environment='production',
        )


def test_payload_does_not_accept_master_projection_scopes_or_different_purpose() -> None:
    pyzipper = pytest.importorskip('pyzipper')
    original, _ = generate_material(
        service_user='operator',
        password=_PASSWORD,
        application_namespace='example',
        environment='production',
    )
    with pyzipper.AESZipFile(BytesIO(original)) as archive:
        archive.setpassword(_PASSWORD.encode())
        manifest = json.loads(archive.read('deployment-access.json'))
    manifest['purpose'] = 'atlanticus.master-projection'
    manifest['allowed_actions'] = ['projection.apply']
    output = BytesIO()
    with pyzipper.AESZipFile(
        output, 'w', compression=pyzipper.ZIP_STORED, encryption=pyzipper.WZ_AES
    ) as archive:
        archive.setpassword(_PASSWORD.encode())
        archive.setencryption(pyzipper.WZ_AES, nbits=256)
        archive.writestr('deployment-access.json', json.dumps(manifest))
    assert inspect_material(output.getvalue()) is MaterialAvailability.PRESENT
    with pytest.raises(DeploymentAccessMaterialError, match='schema'):
        unlock_material(
            output.getvalue(),
            service_user='operator',
            password=_PASSWORD,
            application_namespace='example',
            environment='production',
        )


def test_rotation_always_produces_distinct_material() -> None:
    pytest.importorskip('pyzipper')
    parameters = {
        'service_user': 'operator',
        'password': _PASSWORD,
        'application_namespace': 'example',
        'environment': 'production',
    }
    first, first_identity = generate_material(**parameters)
    second, second_identity = generate_material(**parameters)
    assert first != second
    assert first_identity.material_id != second_identity.material_id
