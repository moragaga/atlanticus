import pytest

pytest.importorskip('dash')
pytest.importorskip('dash_bootstrap_components')

from ada.web.access.configuration.models import AdaAccessConfiguration
from ada.web.access.configuration.web.layout import (
    render_access_catalog,
    render_profile_assignments,
)
from ada.web.access.models import ProfileAccessGrant
from atlanticus.web.profiles.models import ProfileCatalog, ProfileDefinition


def test_access_catalog_renders_stable_access_keys() -> None:
    rendered = render_access_catalog(
        AdaAccessConfiguration(access_keys=('alarms.manage', 'alarms.view'))
    )

    text = str(rendered)
    assert 'alarms.manage' in text
    assert 'alarms.view' in text


def test_profile_assignments_render_projected_profiles_and_current_access() -> None:
    profiles = ProfileCatalog(
        profiles=(
            ProfileDefinition(
                key='operator',
                label='Operator',
                background_color='#123456',
            ),
        )
    )
    configuration = AdaAccessConfiguration(
        access_keys=('alarms.view',),
        profile_access=(
            ProfileAccessGrant(
                profile_key='operator',
                access_keys=('alarms.view',),
            ),
        ),
    )

    rendered = render_profile_assignments(configuration, profiles)

    text = str(rendered)
    assert 'Operator' in text
    assert 'operator' in text
    assert 'alarms.view' in text
