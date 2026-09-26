from application.composition import create_application_definition
from atlanticus.web.application import create_web_application, run_web_application


def run_application() -> None:
    run_web_application(create_web_application(create_application_definition()))
