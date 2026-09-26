from ada.web.application.generic.host import run_operational_application

from application.composition import create_composition


def run_application() -> None:
    run_operational_application(composition_factory=create_composition)
