# Entrypoint local equivalente al usado por ADA Configuration Manager.
from ada_command_center.web.application.configuration_manager.local_runtime import (
    create_local_configuration_manager_application,
)
from atlanticus.web.application import run_web_application


def main() -> None:
    runtime = create_local_configuration_manager_application()
    run_web_application(runtime)


if __name__ == '__main__':
    main()
