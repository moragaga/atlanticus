from __future__ import annotations

import os

from ada.web.application.configuration_manager.local_runtime import (
    create_local_configuration_manager_stores,
)
from ada.web.application.generic.bootstrap import create_operational_application_runtime
from ada.web.application.generic.settings import AdaGenericSettings
from atlanticus.web.application import run_web_application
from atlanticus.web.identity.local import LocalIdentityProvider
from atlanticus.web.users.local import select_local_user


def main() -> None:
    settings = AdaGenericSettings()
    if settings.environment.is_local:
        selected = (
            os.getenv('ATLANTICUS_LOCAL_IDENTITY_SUBJECT_ID') or select_local_user().subject_id
        )
        runtime = create_operational_application_runtime(
            settings=settings,
            manager_stores=create_local_configuration_manager_stores(),
            identity_provider=LocalIdentityProvider(subject_id=selected),
        )
    else:
        runtime = create_operational_application_runtime(settings=settings)
    run_web_application(runtime)


if __name__ == '__main__':
    main()
