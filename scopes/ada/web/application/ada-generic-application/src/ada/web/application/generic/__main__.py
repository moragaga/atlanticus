from ada.web.application.generic.runtime import create_application_runtime
from atlanticus.web.application import run_web_application


def main() -> None:
    runtime = create_application_runtime()
    run_web_application(runtime)


if __name__ == '__main__':
    main()
