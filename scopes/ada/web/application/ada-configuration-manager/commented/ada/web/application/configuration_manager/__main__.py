# Espejo pedagógico: permite ejecutar el Configuration Manager local para validación manual.
from ada.web.application.configuration_manager.local_runtime import (
    create_local_configuration_manager_application,
)
from atlanticus.web.application import run_web_application


# Este entrypoint levanta la composición local real para validar el Manager manualmente.
def main() -> None:
    runtime = create_local_configuration_manager_application()
    run_web_application(runtime)


if __name__ == '__main__':
    main()
