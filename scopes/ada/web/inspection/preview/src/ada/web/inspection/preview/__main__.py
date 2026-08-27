from atlanticus.web.application import run_web_application

from .runtime import create_preview_runtime


def main() -> None:
    run_web_application(create_preview_runtime())


if __name__ == '__main__':
    main()
