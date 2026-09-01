from pathlib import Path

from atlanticus.web.users.configuration import (
    UserProfileConfiguration,
    UsersConfigurationBundle,
    UsersConfigurationCatalog,
)
from atlanticus.web.users.configuration.adapters import (
    FileUsersConfigurationSettings,
    FileUsersConfigurationStore,
    FileUsersProjectionProfileCatalog,
    FileUsersProjectionRepository,
)


def test_file_source_and_projection_are_independent(tmp_path: Path) -> None:
    source_settings = FileUsersConfigurationSettings(root=tmp_path / 'source')
    projection_settings = FileUsersConfigurationSettings(root=tmp_path / 'projection')
    source = FileUsersConfigurationStore(source_settings)
    projection = FileUsersProjectionRepository(projection_settings)
    bundle = UsersConfigurationBundle.create(
        catalog=UsersConfigurationCatalog(
            administrator_background_color='#673AB7',
            guest_background_color='#FF5722',
        ),
        saved_by='administrator',
    )

    source.publish_bundle(bundle, expected_source_revision=None)

    assert source.fetch_bundle().revision == bundle.revision
    assert projection.load_state() is None

    state = projection.project(bundle, actor='administrator')

    assert projection.load_state().revision == state.revision
    assert source.fetch_bundle().revision == bundle.revision


def test_file_projection_profile_catalog_uses_defaults_before_first_projection(
    tmp_path: Path,
) -> None:
    repository = FileUsersProjectionRepository(
        FileUsersConfigurationSettings(root=tmp_path / 'projection')
    )
    profiles = FileUsersProjectionProfileCatalog(repository)

    assert profiles.require('administrator').label == 'Administrador'
    assert profiles.custom_profiles == ()


def test_file_projection_profile_catalog_reflects_latest_projected_catalog(tmp_path: Path) -> None:
    repository = FileUsersProjectionRepository(
        FileUsersConfigurationSettings(root=tmp_path / 'projection')
    )
    profiles = FileUsersProjectionProfileCatalog(repository)
    first = UsersConfigurationBundle.create(
        catalog=UsersConfigurationCatalog(
            administrator_background_color='#112233',
            guest_background_color='#445566',
            profiles=(
                UserProfileConfiguration(
                    key='operator',
                    label='Operador',
                    background_color='#778899',
                ),
            ),
        ),
        saved_by='administrator',
    )
    second = UsersConfigurationBundle.create(
        catalog=UsersConfigurationCatalog(
            administrator_background_color='#AABBCC',
            guest_background_color='#DDEEFF',
            profiles=(
                UserProfileConfiguration(
                    key='dispatcher',
                    label='Despachador',
                    background_color='#123456',
                ),
            ),
        ),
        saved_by='administrator',
    )

    repository.project(first, actor='administrator')

    assert profiles.administrator_background_color == '#112233'
    assert profiles.require('operator').label == 'Operador'

    repository.project(second, actor='administrator')

    assert profiles.administrator_background_color == '#AABBCC'
    assert profiles.require('dispatcher').label == 'Despachador'
