# En el perfil genérico, Atlanticus compone Flask, Dash y assets.
from atlanticus.web.application import create_web_application, run_web_application

from application.composition import create_application_definition


def run_application() -> None:
    run_web_application(create_web_application(create_application_definition()))
