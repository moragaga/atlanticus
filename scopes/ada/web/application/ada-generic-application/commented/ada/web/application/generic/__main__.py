# Entry point local de la aplicación ADA genérica.
from ada.web.application.generic.runtime import create_application_runtime
from atlanticus.web.application import run_web_application


def main() -> None:
    # La aplicación sólo compone capacidades; la infraestructura externa se conectará después.
    runtime = create_application_runtime()
    run_web_application(runtime)


if __name__ == '__main__':
    main()
