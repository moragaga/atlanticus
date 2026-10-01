from __future__ import annotations

import pytest

from ada.web.application.configuration_manager.local_runtime import (
    create_local_configuration_manager_stores,
)
from ada.web.application.generic.manager_principal import (
    compose_integrated_manager_dependencies,
)
from atlanticus.web.configuration import WebEnvironment
from atlanticus.web.identity.access import AccessRuntime
from atlanticus.web.users.runtime import UsersRuntime


@pytest.mark.parametrize(
    ('source_name', 'projection_name'),
    (
        ('Local Source', 'Local Projection'),
        ('Blob Storage', 'Cosmos DB'),
    ),
)
def test_manager_uses_injected_provider_names_for_all_modules(
    tmp_path, source_name, projection_name
):
    stores = create_local_configuration_manager_stores(source_root=tmp_path / 'source')
    dependencies = compose_integrated_manager_dependencies(
        stores=stores,
        access_runtime=AccessRuntime(),
        users_runtime=UsersRuntime(),
        environment=WebEnvironment.LOCAL,
        source_name=source_name,
        projection_name=projection_name,
    )
    assert dependencies.profiles_module.source_name == source_name
    assert dependencies.profiles_module.projection_name == projection_name
    assert dependencies.navigation_module.source_name == source_name
    assert dependencies.navigation_module.projection_name == projection_name
    for kind in ('tools', 'access', 'kpi_registry', 'kpi_definitions'):
        assert getattr(dependencies, f'{kind}_source_name') == source_name
        assert getattr(dependencies, f'{kind}_projection_name') == projection_name
