from pathlib import Path

from ada_command_center.web.application.configuration_manager.catalog_configuration import (
    ManagerConfigurationReader,
)
from ada_command_center.web.application.generic.runtime import open_local_application
from atlanticus.web.application import run_web_application


def main() -> None:
    reader = ManagerConfigurationReader(root=Path.cwd())
    with open_local_application(reader=reader) as runtime:
        run_web_application(runtime)


if __name__ == '__main__':
    main()
