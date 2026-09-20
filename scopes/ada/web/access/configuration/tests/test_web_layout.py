import pytest

pytest.importorskip('dash')
pytest.importorskip('dash_bootstrap_components')

from ada.web.access.configuration.models import AdaAccessConfiguration
from ada.web.access.configuration.web.layout import (
    access_catalog_page,
    profile_assignment_page,
    render_profile_access_editor,
    render_profile_assignments,
)
from ada.web.access.models import ProfileAccessGrant
from atlanticus.web.pagination import PageRequest
from atlanticus.web.profiles.models import ProfileCatalog, ProfileDefinition


def test_access_catalog_page_paginates_stable_access_keys() -> None:
    configuration = AdaAccessConfiguration(
        access_keys=tuple(f'area{index:02d}.view' for index in range(12)),
    )

    first = access_catalog_page(configuration, PageRequest(page_number=1, page_size=10))
    second = access_catalog_page(configuration, PageRequest(page_number=2, page_size=10))

    assert first.total_count == 12
    assert len(first.items) == 10
    assert second.items == ('area10.view', 'area11.view')


def test_profile_assignment_page_falls_back_to_assignable_system_profiles() -> None:
    page = profile_assignment_page(
        None,
        PageRequest(page_number=1, page_size=10),
    )

    assert tuple(profile.key for profile in page.items) == ('basic', 'guest')


def test_profile_assignment_page_excludes_unrestricted_profiles() -> None:
    profiles = ProfileCatalog(
        profiles=(
            ProfileDefinition(
                key='operator',
                label='Operator',
                background_color='#123456',
            ),
        )
    )

    page = profile_assignment_page(
        profiles,
        PageRequest(page_number=1, page_size=10),
    )

    assert tuple(profile.key for profile in page.items) == ('basic', 'guest', 'operator')


def test_profile_assignment_page_paginates_assignable_profiles() -> None:
    profiles = ProfileCatalog(
        profiles=tuple(
            ProfileDefinition(
                key=f'profile-{index:02d}',
                label=f'Profile {index:02d}',
                background_color='#123456',
            )
            for index in range(15)
        )
    )

    first = profile_assignment_page(
        profiles,
        PageRequest(page_number=1, page_size=10),
    )
    second = profile_assignment_page(
        profiles,
        PageRequest(page_number=2, page_size=10),
    )

    assert first.total_count == 17
    assert len(first.items) == 10
    assert len(second.items) == 7
    assert all(profile.key not in {'root', 'local'} for profile in (*first.items, *second.items))


def test_profile_assignment_rows_summarize_access_without_rendering_selection() -> None:
    configuration = AdaAccessConfiguration(
        access_keys=('alarms.view', 'kpis.view', 'navigation.view'),
        profile_access=(
            ProfileAccessGrant(
                profile_key='basic',
                access_keys=('alarms.view', 'kpis.view', 'navigation.view'),
            ),
        ),
    )
    page = profile_assignment_page(None, PageRequest())

    rendered = render_profile_assignments(configuration, page)
    text = str(rendered)

    assert '3 accesos' in text
    assert 'Configurar' in text
    assert 'alarms.view' not in text
    assert 'kpis.view' not in text
    assert 'navigation.view' not in text


def test_profile_access_editor_marks_only_current_assignments() -> None:
    configuration = AdaAccessConfiguration(
        access_keys=('alarms.view', 'kpis.view'),
    )

    rendered = render_profile_access_editor(
        configuration,
        selected=('alarms.view',),
    )
    text = str(rendered)

    assert 'alarms.view' in text
    assert 'kpis.view' in text
    assert text.count('value=True') == 1
