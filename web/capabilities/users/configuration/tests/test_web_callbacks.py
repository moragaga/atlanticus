import pytest

pytest.importorskip('dash')

from atlanticus.web.manager.projection import ManagerDraft
from atlanticus.web.users.configuration.models import (
    DiscoveredUser,
    UserConfiguration,
    UsersConfigurationCatalog,
    build_user_key,
)
from atlanticus.web.users.configuration.web.callbacks import (
    _browser_draft_document,
    _save_profile,
    _save_user,
)
from atlanticus.web.users.profiles import (
    DEFAULT_ADMINISTRATOR_BACKGROUND_COLOR,
    DEFAULT_ADMINISTRATOR_TEXT_COLOR,
    DEFAULT_GUEST_BACKGROUND_COLOR,
    DEFAULT_GUEST_TEXT_COLOR,
)


def _catalog() -> UsersConfigurationCatalog:
    return UsersConfigurationCatalog(
        administrator_background_color=DEFAULT_ADMINISTRATOR_BACKGROUND_COLOR,
        administrator_text_color=DEFAULT_ADMINISTRATOR_TEXT_COLOR,
        guest_background_color=DEFAULT_GUEST_BACKGROUND_COLOR,
        guest_text_color=DEFAULT_GUEST_TEXT_COLOR,
    )


def _with_operator() -> UsersConfigurationCatalog:
    return _save_profile(
        _catalog(),
        {'mode': 'create'},
        'Operador Planta',
        '#C9A24B',
        '#071522',
    )


def _discovered() -> DiscoveredUser:
    return DiscoveredUser(
        user_id=build_user_key(issuer='entra', subject_id='subject-1'),
        issuer='entra',
        subject_id='subject-1',
        display_name='Usuario Descubierto',
        email='discovered@example.com',
    )


def test_profile_editor_generates_stable_key_and_user_can_consume_it() -> None:
    with_profile = _with_operator()
    with_user = _save_user(
        with_profile,
        {
            'mode': 'discovered',
            'user_id': build_user_key(issuer='entra', subject_id='subject-one'),
            'issuer': 'entra',
            'subject_id': 'subject-one',
        },
        display_name='Usuario Uno',
        email='user.one@example.com',
        profile_key='operador_planta',
        enabled=True,
    )

    profile = with_profile.profiles[0]
    assert profile.key == 'operador_planta'
    assert profile.background_color == '#C9A24B'
    assert profile.text_color == '#071522'
    assert with_user.users[0].profile_key == 'operador_planta'


def test_discovered_user_keeps_identity_when_added_to_draft() -> None:
    updated = _save_user(
        _with_operator(),
        {
            'mode': 'discovered',
            'user_id': build_user_key(issuer='entra', subject_id='subject-1'),
            'issuer': 'entra',
            'subject_id': 'subject-1',
        },
        display_name='Usuario Descubierto',
        email='discovered@example.com',
        profile_key='operador_planta',
        enabled=True,
    )

    user = updated.users[0]
    assert user.user_id == build_user_key(issuer='entra', subject_id='subject-1')
    assert user.issuer == 'entra'
    assert user.subject_id == 'subject-1'


def test_discovered_identity_with_existing_email_is_not_rebound() -> None:
    base = _with_operator()
    existing = UserConfiguration.create(
        display_name='Usuario Descubierto',
        email='discovered@example.com',
        profile_key='operador_planta',
        issuer='entra',
        subject_id='existing-subject',
    )
    catalog = UsersConfigurationCatalog(
        administrator_background_color=base.administrator_background_color,
        administrator_text_color=base.administrator_text_color,
        guest_background_color=base.guest_background_color,
        guest_text_color=base.guest_text_color,
        profiles=base.profiles,
        users=(existing,),
    )
    discovered = _discovered()

    with pytest.raises(ValueError, match='User email already exists'):
        _save_user(
            catalog,
            {
                'mode': 'discovered',
                'user_id': discovered.user_id,
                'issuer': discovered.issuer,
                'subject_id': discovered.subject_id,
            },
            display_name=discovered.display_name,
            email=discovered.email,
            profile_key='operador_planta',
            enabled=True,
        )

    assert catalog.users == (existing,)


def test_users_browser_draft_is_accepted_by_manager_contract() -> None:
    catalog = _with_operator()

    document = _browser_draft_document(
        catalog=catalog,
        owner_subject_id='administrator-local',
        base_source_revision=None,
    )

    draft = ManagerDraft.from_document(document)

    assert draft.owner_subject_id == 'administrator-local'
    assert draft.payload == catalog.to_document()
