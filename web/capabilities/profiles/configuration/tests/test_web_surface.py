import pytest

pytest.importorskip('dash')
pytest.importorskip('dash_bootstrap_components')

from atlanticus.web.pagination import PageRequest
from atlanticus.web.profiles.configuration import ProfilesConfiguration
from atlanticus.web.profiles.configuration.web import (
    LocalIdentityBadge,
    ProfilesAdminWebContext,
    configured_profiles_page,
    create_profiles_admin_web_module,
)
from atlanticus.web.profiles.models import ProfileDefinition


def _profile(index: int) -> ProfileDefinition:
    return ProfileDefinition(
        key=f'profile-{index}',
        label=f'Perfil {index}',
        background_color='#123456',
    )


def _context() -> ProfilesAdminWebContext:
    return ProfilesAdminWebContext(
        workspace_payload_reader=lambda document: None if document is None else document['payload'],
        workspace_payload_writer=lambda _document, payload: {'payload': payload},
        local_identity_badges_provider=lambda: (
            LocalIdentityBadge(
                display_name='Jane Doe',
                background_color='#C85D91',
                text_color='#FFFFFF',
            ),
            LocalIdentityBadge(
                display_name='John Doe',
                background_color='#3778C2',
                text_color='#FFFFFF',
            ),
        ),
        draft_store_id='draft',
        saved_draft_store_id='saved',
        draft_save_action_id='save-action',
        editor_revision_store_id='editor-revision',
    )


def test_local_identity_badge_normalizes_visual_contract() -> None:
    badge = LocalIdentityBadge(
        display_name=' Jane Doe ',
        background_color=' #c85d91 ',
        text_color=' #ffffff ',
    )

    assert badge.display_name == 'Jane Doe'
    assert badge.background_color == '#C85D91'
    assert badge.text_color == '#FFFFFF'


def test_configured_profiles_page_excludes_system_profiles() -> None:
    configuration = ProfilesConfiguration(
        profiles=tuple(_profile(index) for index in range(1, 13))
    )

    page = configured_profiles_page(
        configuration,
        PageRequest(page_number=1, page_size=10),
    )

    assert page.total_count == 12
    assert len(page.items) == 10
    assert all(profile.key not in {'basic', 'root', 'guest', 'local'} for profile in page.items)


def test_configured_profiles_page_uses_generic_clamp_and_page_size() -> None:
    configuration = ProfilesConfiguration(
        profiles=tuple(_profile(index) for index in range(1, 13))
    )

    page = configured_profiles_page(
        configuration,
        PageRequest(page_number=9, page_size=10),
    )

    assert page.request.page_number == 2
    assert [profile.label for profile in page.items] == ['Perfil 11', 'Perfil 12']


def test_profiles_admin_web_module_registers_owned_asset_layer() -> None:
    module = create_profiles_admin_web_module(_context())

    assert module.name == 'atlanticus-profiles-configuration'
    assert len(module.asset_layers) == 1
    assert module.asset_layers[0].name == 'atlanticus_profiles_configuration'
    assert module.asset_layers[0].package == 'atlanticus.web.profiles.configuration'
    assert module.register_callbacks is not None
