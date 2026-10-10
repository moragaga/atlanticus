from dataclasses import replace

import pytest

from atlanticus.web.profiles.models import BASIC_PROFILE
from atlanticus.web.users.errors import UsersDefinitionError
from atlanticus.web.users.identity import build_user_key
from atlanticus.web.users.models import (
    RuntimeOperational,
    RuntimeOperationalReference,
    RuntimeProfile,
    RuntimeUser,
    ToolUserMembership,
    UserIdentity,
    build_runtime_user,
)


def _identity() -> UserIdentity:
    issuer = 'tenant-a'
    subject = 'alice'
    return UserIdentity(
        user_id=build_user_key(issuer=issuer, subject_id=subject),
        issuer=issuer,
        subject_id=subject,
        display_name='Alice',
    )


def test_runtime_contract_preserves_resolved_access_and_operational_data():
    identity = _identity()
    runtime = build_runtime_user(
        identity=identity,
        membership=ToolUserMembership(user_id=identity.user_id, profile_key='basic'),
        profile=BASIC_PROFILE,
        access_keys=('dashboard.view', 'reports.read'),
        operational=RuntimeOperational(
            area=RuntimeOperationalReference(id='mina', label='Mina'),
            position=RuntimeOperationalReference(id='operator', label='Operador'),
            group=RuntimeOperationalReference(id=2, label='Grupo 2'),
        ),
    )

    document = runtime.to_document()
    assert set(document) == {'identity', 'enabled', 'profile', 'access_keys', 'operational'}
    assert document['access_keys'] == ['dashboard.view', 'reports.read']
    assert RuntimeUser.from_document(document) == runtime
    assert RuntimeUser.from_document(document).operational == runtime.operational


@pytest.mark.parametrize(
    'keys',
    [
        ('dashboard.view', 'dashboard.view'),
        ('reports.read', 'dashboard.view'),
        ('Dashboard.View',),
        ('dashboard view',),
        ('',),
        ('dashboard.view', 7),
        ['dashboard.view'],
        'dashboard.view',
    ],
)
def test_runtime_rejects_noncanonical_access_keys(keys):
    with pytest.raises(UsersDefinitionError):
        RuntimeUser(
            identity=_identity(),
            enabled=True,
            profile=RuntimeProfile.from_profile(BASIC_PROFILE),
            access_keys=keys,
        )


@pytest.mark.parametrize('mutation', ['missing', 'extra', 'bad_type', 'invalid_key'])
def test_serialized_runtime_contract_rejects_malformed_documents(mutation):
    base = RuntimeUser(
        identity=_identity(),
        enabled=True,
        profile=RuntimeProfile.from_profile(BASIC_PROFILE),
        access_keys=('dashboard.view',),
    )
    document = base.to_document()
    if mutation == 'missing':
        del document['access_keys']
    elif mutation == 'extra':
        document['legacy_access'] = []
    elif mutation == 'bad_type':
        document['access_keys'] = 'dashboard.view'
    else:
        document['access_keys'] = ['Dashboard.View']
    with pytest.raises(UsersDefinitionError):
        RuntimeUser.from_document(document)


def test_runtime_access_can_be_replaced_without_changing_identity_or_operational_data():
    original = RuntimeUser(
        identity=_identity(),
        enabled=True,
        profile=RuntimeProfile.from_profile(BASIC_PROFILE),
        access_keys=('dashboard.view',),
    )
    updated = replace(original, access_keys=('dashboard.view', 'reports.read'))
    assert updated.identity == original.identity
    assert updated.operational == original.operational
    assert updated.access_keys == ('dashboard.view', 'reports.read')
