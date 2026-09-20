import pytest

from ada.web.access.configuration import (
    AdaAccessConfiguration,
    create_access_key,
    remove_access_key,
    set_profile_access,
)
from ada.web.access.errors import AdaAccessDefinitionError


def test_create_access_key_adds_normalized_stable_identifier() -> None:
    updated = create_access_key(
        AdaAccessConfiguration(),
        access_key=' Alarms.View ',
    )

    assert updated.access_keys == ('alarms.view',)


def test_create_access_key_rejects_duplicate_identifier() -> None:
    configuration = AdaAccessConfiguration(access_keys=('alarms.view',))

    with pytest.raises(AdaAccessDefinitionError, match='already exists'):
        create_access_key(configuration, access_key='ALARMS.VIEW')


def test_set_profile_access_assigns_only_defined_access_keys() -> None:
    configuration = AdaAccessConfiguration(
        access_keys=('alarms.manage', 'alarms.view'),
    )

    updated = set_profile_access(
        configuration,
        profile_key='Operator',
        access_keys=('alarms.view', 'alarms.manage'),
    )

    assert len(updated.profile_access) == 1
    assert updated.profile_access[0].profile_key == 'operator'
    assert updated.profile_access[0].access_keys == ('alarms.view', 'alarms.manage')


def test_set_profile_access_rejects_undefined_access_key() -> None:
    configuration = AdaAccessConfiguration(access_keys=('alarms.view',))

    with pytest.raises(AdaAccessDefinitionError, match='undefined access key'):
        set_profile_access(
            configuration,
            profile_key='operator',
            access_keys=('alarms.manage',),
        )


def test_set_profile_access_with_empty_access_removes_sparse_grant() -> None:
    configured = set_profile_access(
        AdaAccessConfiguration(access_keys=('alarms.view',)),
        profile_key='operator',
        access_keys=('alarms.view',),
    )

    updated = set_profile_access(
        configured,
        profile_key='operator',
        access_keys=(),
    )

    assert updated.profile_access == ()


def test_remove_access_key_requires_assignments_to_be_removed_first() -> None:
    configuration = set_profile_access(
        AdaAccessConfiguration(access_keys=('alarms.view',)),
        profile_key='operator',
        access_keys=('alarms.view',),
    )

    with pytest.raises(AdaAccessDefinitionError, match='still assigned'):
        remove_access_key(configuration, access_key='alarms.view')


def test_remove_access_key_removes_unassigned_definition() -> None:
    configuration = AdaAccessConfiguration(
        access_keys=('alarms.manage', 'alarms.view'),
    )

    updated = remove_access_key(configuration, access_key='alarms.view')

    assert updated.access_keys == ('alarms.manage',)
