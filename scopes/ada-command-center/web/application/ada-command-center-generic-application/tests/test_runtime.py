import pytest

from ada_command_center.web.application.configuration_manager.catalog_configuration import (
    ManagerConfigurationReader,
)
from ada_command_center.web.application.generic.runtime import open_local_application
from atlanticus.web.identity.errors import IdentityConfigurationError


def test_local_launcher_rejects_production_before_opening_manager(tmp_path) -> None:
    reader = ManagerConfigurationReader(
        root=tmp_path,
        environ_supplier=lambda: {'ATLANTICUS_ENVIRONMENT': 'production'},
    )

    with (
        pytest.raises(
            IdentityConfigurationError,
            match='injected production identity provider',
        ),
        open_local_application(reader=reader),
    ):
        pass
